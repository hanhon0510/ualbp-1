from pysat.solvers import Glucose3
import csv
import os
import time
import threading
from multiprocessing import Process, Queue
from pysat.pb import EncType, PBEnc

CURRENT_SOLVER = None

def read_ualbp_file(file_path):
    with open(file_path, 'r') as file:
        lines = file.readlines()
    
    n = int(lines[0].strip())
    tasks = [int(lines[i + 1].strip()) for i in range(n)]
    
    precedences = []
    for line in lines[n + 1:]:
        i, j = map(int, line.strip().split(','))
        if i == -1 and j == -1:
            break
        precedences.append((i - 1, j - 1))
    
    return n, tasks, precedences

def generate_ualbp_variables(num_tasks, num_stations):
    return [[(i * num_stations * 2 + k + 1,
              i * num_stations * 2 + num_stations + k + 1)
             for k in range(num_stations)] for i in range(num_tasks)]

def generate_base_clauses(num_tasks, num_stations, tasks, precedences, variables):
   
    clauses = []
    
    # Assignment constraints: each task must be assigned exactly once (in either mode)
    for i in range(num_tasks):
        # At least one assignment (forward or backward)
        clauses.append([variables[i][k][0] for k in range(num_stations)] +
                       [variables[i][k][1] for k in range(num_stations)])
        
        # In each station, task cannot be assigned in both modes
        for k in range(num_stations):
            clauses.append([-variables[i][k][0], -variables[i][k][1]])
        
        # Task i is assigned in at most one station per mode
        for k1 in range(num_stations):
            for k2 in range(k1 + 1, num_stations):
                clauses.append([-variables[i][k1][0], -variables[i][k2][0]])
                clauses.append([-variables[i][k1][1], -variables[i][k2][1]])
    
    # Precedence constraints
    for i, j in precedences:
        # Forward pass
        for k in range(num_stations):
            for h in range(num_stations):
                if k >= h:
                    clauses.append([-variables[i][k][0], -variables[j][h][0]])
        # Backward pass
        for k in range(num_stations):
            for h in range(num_stations):
                if k <= h:
                    clauses.append([-variables[i][k][1], -variables[j][h][1]])
        # i assigned backward and j assigned forward
        for k in range(num_stations):
            for h in range(num_stations):
                clauses.append([-variables[i][k][1], -variables[j][h][0]])
    
    offset = num_tasks * num_stations * 2
    y_vars = [[offset + i * num_stations + k + 1 for k in range(num_stations)]
              for i in range(num_tasks)]
    
    for i in range(num_tasks):
        for k in range(num_stations):
            Xik, Wik = variables[i][k][0], variables[i][k][1]
            yik = y_vars[i][k]
            # y => (X or W):  ¬y ∨ X ∨ W
            clauses.append([-yik, Xik, Wik])
            # X => y:  ¬X ∨ y
            clauses.append([-Xik, yik])
            # W => y:  ¬W ∨ y
            clauses.append([-Wik, yik])
    
    return clauses, y_vars

def check_cycle_time(model, num_tasks, num_stations, tasks, y_vars, cycle_time):
    violations = []
    for k in range(num_stations):
        total = 0
        assigned = []
        for i in range(num_tasks):
            if model[y_vars[i][k] - 1] > 0:
                total += tasks[i]
                assigned.append(i)
        if total > cycle_time:
            violations.append((k, assigned, total))
    return violations

def solve_ualbp_iterative(num_tasks, num_stations, tasks, precedences, cycle_time):

    global CURRENT_SOLVER
    variables = generate_ualbp_variables(num_tasks, num_stations)
    base_clauses, y_vars = generate_base_clauses(num_tasks, num_stations, tasks, precedences, variables)
    
    extra_clauses = []
    iteration = 0
    while True:
        iteration += 1
        print(f"Iteration {iteration}: Solving SAT with {len(base_clauses) + len(extra_clauses)} clauses...", flush=True)
        solver = Glucose3()
        CURRENT_SOLVER = solver
        for clause in base_clauses + extra_clauses:
            solver.add_clause(clause)
        if not solver.solve():
            print("No solution found (unsat after adding cycle-time cuts).", flush=True)
            return None
        model = solver.get_model()
        violations = check_cycle_time(model, num_tasks, num_stations, tasks, y_vars, cycle_time)
        if not violations:
            solution = [[] for _ in range(num_stations)]
            for i in range(num_tasks):
                for k in range(num_stations):
                    if model[variables[i][k][0] - 1] > 0:
                        solution[k].append(f"{i}F")
                    elif model[variables[i][k][1] - 1] > 0:
                        solution[k].append(f"{i}B")
            return solution
        else:
            for (k, assigned_tasks, total) in violations:
                print(f"Cycle-time violation at station {k+1}: tasks {assigned_tasks} sum to {total} (bound={cycle_time}).", flush=True)
                clause = [-y_vars[i][k] for i in assigned_tasks]
                extra_clauses.append(clause)
            print("Added cycle-time cut(s). Re-solving...", flush=True)
        solver.delete()

def solve_ualbp(num_tasks, num_stations, tasks, precedences, cycle_time):
    current_num_stations = num_stations
    solution = solve_ualbp_iterative(num_tasks, current_num_stations, tasks, precedences, cycle_time)
    while solution is None:
        current_num_stations += 1
        solution = solve_ualbp_iterative(num_tasks, current_num_stations, tasks, precedences, cycle_time)
    return solution, current_num_stations

def solver_process(num_tasks, num_stations, tasks, precedences, cycle_time, queue):
    result = solve_ualbp(num_tasks, num_stations, tasks, precedences, cycle_time)
    queue.put(result)

def solve_instance_with_timeout(num_tasks, num_stations, tasks, precedences, cycle_time, timeout=60):
    q = Queue()
    p = Process(target=solver_process, args=(num_tasks, num_stations, tasks, precedences, cycle_time, q))
    start_time = time.time()
    p.start()
    p.join(timeout)
    elapsed_time = time.time() - start_time
    if p.is_alive():
        print(f"Timeout reached after {elapsed_time:.2f} seconds. Terminating solver process...", flush=True)
        p.terminate()
        p.join()
        return None, "TLE", "TLE"
    else:
        if not q.empty():
            solution, final_num_stations = q.get()
            return solution, final_num_stations, elapsed_time
        else:
            return None, "TLE", "TLE"


def write_solution_to_txt(instance_name, solution, final_num_stations, txt_file):
    with open(txt_file, 'a') as f:
        f.write(f"Instance: {instance_name}, Final Stations: {final_num_stations}\n")
        for i, station in enumerate(solution):
            f.write(f"Station {i+1}: {' '.join(station)}\n")
        f.write("\n")

def process_instances(csv_file, output_csv, output_txt, start_row, end_row):
    results = []
    with open(csv_file, newline='') as f:
        reader = csv.DictReader(f)
        for row_index, row in enumerate(reader, start=1):
            if row_index < start_row:
                continue
            if row_index > end_row:
                break
            
            full_name = row['name'].strip()
            try:
                value = row['lb'].strip()
                lb = 1 if value == 'NA' else int(value)

            except Exception as e:
                print(f"Error parsing lb in row: {row} : {e}")
                continue
            
            parts = full_name.rsplit('-', 1)
            if len(parts) != 2:
                print(f"Skipping row with invalid name format: {full_name}")
                continue
            instance_name = parts[0]

            try:
                cycle_time = int(parts[1])
            except Exception as e:
                print(f"Error parsing cycle_time from {full_name}: {e}")
                continue
            
            instance_file = f"dataset/{instance_name}"
            try:
                num_tasks, tasks, precedences_inst = read_ualbp_file(instance_file)
            except Exception as e:
                print(f"Error reading instance file {instance_file}: {e}")
                continue
            
            print(f"Processing row {row_index}, {full_name}: cycle_time={cycle_time}, initial stations (lb)={lb}", flush=True)
            
            solution, final_num_stations, elapsed_time = solve_instance_with_timeout(
                num_tasks, lb, tasks, precedences_inst, cycle_time, timeout=900)
            
            if elapsed_time == "TLE":
                results.append({
                    'name': full_name,
                    'lb': lb,
                    'final_num_stations': "TLE",
                    'time': "TLE"
                })
                print(f"Row {row_index} timed out", flush=True)
            else:
                results.append({
                    'name': full_name,
                    'lb': lb,
                    'final_num_stations': final_num_stations,
                    'time': f"{elapsed_time:.2f}"
                })
                write_solution_to_txt(full_name, solution, final_num_stations, output_txt)
    
    with open(output_csv, 'w', newline='') as out:
        fieldnames = ['name', 'lb', 'final_num_stations', 'time']
        writer = csv.DictWriter(out, fieldnames=fieldnames)
        writer.writeheader()
        for res in results:
            writer.writerow(res)
    
    print(f"Summary results exported to {output_csv}", flush=True)
    print(f"Detailed solutions exported to {output_txt}", flush=True)

if __name__ == '__main__':
    result_folder = "result"
    if not os.path.exists(result_folder):
        os.makedirs(result_folder)
    
    input_csv = "standard_t5.csv"
    output_csv = os.path.join(result_folder, "results_naive.csv")
    output_txt = os.path.join(result_folder, "solutions3.txt")

    with open(output_txt, 'w') as f:
        f.write("")
    
    process_instances(input_csv, output_csv, output_txt, start_row=1, end_row=269)
