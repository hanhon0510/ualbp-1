from pysat.solvers import Glucose3
import csv
import os
import time
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
    """
    Returns a nested list for each task and each station.
    Each element is a tuple: (forward_literal, backward_literal)
    """
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
        # Forward pass: if task i precedes task j then for stations k>=h
        for k in range(num_stations):
            for h in range(num_stations):
                if k >= h:
                    clauses.append([-variables[i][k][0], -variables[j][h][0]])
        # Backward pass:
        for k in range(num_stations):
            for h in range(num_stations):
                if k <= h:
                    clauses.append([-variables[i][k][1], -variables[j][h][1]])
        # Mixed: task i assigned backward and task j assigned forward
        for k in range(num_stations):
            for h in range(num_stations):
                clauses.append([-variables[i][k][1], -variables[j][h][0]])
    return clauses

def decode_solution(model, variables):
    assignment = {}
    for i, task_vars in enumerate(variables):
        assigned = False
        for s, (fwd, bwd) in enumerate(task_vars):
            if fwd in model:
                assignment[i] = (s, 'F')
                assigned = True
                break
            if bwd in model:
                assignment[i] = (s, 'B')
                assigned = True
                break
        if not assigned:
            assignment[i] = None
    return assignment

def solve_ualbp_iterative(num_tasks, num_stations, tasks, precedences, cycle_time):
    global CURRENT_SOLVER
    variables = generate_ualbp_variables(num_tasks, num_stations)
    base_clauses = generate_base_clauses(num_tasks, num_stations, tasks, precedences, variables)
    extra_clauses = []
    iteration = 0
    while True:
        iteration += 1
        print(f"Iteration {iteration}: Solving SAT with {len(base_clauses) + len(extra_clauses)} clauses...", flush=True)
        solver = Glucose3()
        CURRENT_SOLVER = solver

        print("Variables:")
        print(variables)
        print("Base clauses:")
        print(base_clauses)

        next_var = num_tasks * num_stations * 2

        for clause in base_clauses + extra_clauses:
            solver.add_clause(clause)

        for s in range(num_stations):
            lits = []
            weights = []
            for i in range(num_tasks):
                lits.append(variables[i][s][0])
                weights.append(tasks[i])
                lits.append(variables[i][s][1])
                weights.append(tasks[i])

            # Using psuedo-boolean to impose the cycle time constraint
            pb_constraint = PBEnc.leq(lits=lits, weights=weights, bound=cycle_time, top_id=next_var, encoding=EncType.best)
            for clause in pb_constraint.clauses:
                solver.add_clause(clause)
            print(f"PB clauses for station {s}:")
            print(pb_constraint.clauses)

            local_max = next_var
            print(f"Local max for station {s}: {local_max}")
            for clause in pb_constraint.clauses:
                local_max = max(local_max, max(abs(l) for l in clause))
            next_var = local_max + 1
            
        if not solver.solve():
            print("No solution found", flush=True)
            solver.delete()
            return None
        else:
            model = solver.get_model()
            decoded = decode_solution(model, variables)
            print("Decoded solution:", decoded)
            solver.delete()
            return decoded

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

def write_solution_to_txt(instance_name, decoded, txt_file):
    station_assignments = {}
    for task, assignment in decoded.items():
        if assignment is None:
            continue
        station, mode = assignment
        assignment_str = f"{task+1}{mode}"
        station_assignments.setdefault(station, []).append(assignment_str)
    
    final_stations = max(station_assignments.keys()) + 1 if station_assignments else 0

    with open(txt_file, 'a') as f:
        f.write(f"Instance: {instance_name}, Final Stations: {final_stations}\n")
        for s in range(final_stations):
            tasks_str = " ".join(sorted(station_assignments.get(s, []), key=lambda x: int(x[:-1]) if x[:-1].isdigit() else x))
            f.write(f"Station {s+1}: {tasks_str}\n")
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
            
            print("Elapsed time:", elapsed_time)
            if elapsed_time == "TLE":
                results.append({
                    'name': full_name,
                    'lb': lb,
                    'final_num_stations': "TLE",
                    'time': "TLE"
                })
                print(f"Row {row_index} timed out.", flush=True)
            else:
                results.append({
                    'name': full_name,
                    'lb': lb,
                    'final_num_stations': final_num_stations,
                    'time': f"{elapsed_time:.2f}"
                })
                if solution is not None:
                    write_solution_to_txt(full_name, solution, output_txt)
                else:
                    # Even if solution is None, we record the result as unsat.
                    with open(output_txt, 'a') as f:
                        f.write(f"Instance: {instance_name}, No solution found.\n\n")
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
    output_csv = os.path.join(result_folder, "results_pb.csv")
    output_txt = os.path.join(result_folder, "solution_pb.txt")
    with open(output_txt, 'w') as f:
        f.write("")

    process_instances(input_csv, output_csv, output_txt, start_row=266, end_row=266)
    # process_instances(input_csv, output_csv, output_txt, start_row=1, end_row=1)