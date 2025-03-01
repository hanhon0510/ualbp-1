from pysat.solvers import Glucose3
from itertools import combinations
import threading
import time

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
    """Generate variables for forward and backward assignments."""
    return [[(i * num_stations * 2 + k + 1,
              i * num_stations * 2 + num_stations + k + 1)
             for k in range(num_stations)] for i in range(num_tasks)]

def encode_cycle_time_rec(y_vars_station, tasks, cycle_time, start, current_subset, current_sum, clauses):
    if current_sum > cycle_time:
        clause = [-y_vars_station[i] for i in current_subset]
        clauses.append(clause)
        return
    
    for i in range(start, len(y_vars_station)):
        new_sum = current_sum + tasks[i]
        new_subset = current_subset + [i]
        if new_sum > cycle_time:
            clause = [-y_vars_station[j] for j in new_subset]
            clauses.append(clause)
        encode_cycle_time_rec(y_vars_station, tasks, cycle_time, i + 1, new_subset, new_sum, clauses)

def generate_ualbp_clauses(num_tasks, num_stations, tasks, precedences, cycle_time, variables):
    clauses = []
    
    # Task assignment constraints: Each task must be assigned exactly once (either forward or backward)
    for i in range(num_tasks):
        # At least one assignment (either mode)
        clauses.append([variables[i][k][0] for k in range(num_stations)] +
                       [variables[i][k][1] for k in range(num_stations)])
        
        # No double assignments in same station
        for k in range(num_stations):
            clauses.append([-variables[i][k][0], -variables[i][k][1]])
        
        # Ensure task is assigned only once per mode
        for k1 in range(num_stations):
            for k2 in range(k1 + 1, num_stations):
                clauses.append([-variables[i][k1][0], -variables[i][k2][0]])
                clauses.append([-variables[i][k1][1], -variables[i][k2][1]])
    
    # Precedence Constraints (i must be scheduled before j)
    for i, j in precedences:
        # Forward pass: disallow i in a later station than j (for forward assignments)
        for k in range(num_stations):
            for h in range(num_stations):
                if k >= h:
                    clauses.append([-variables[i][k][0], -variables[j][h][0]])
        # Backward pass: disallow i in a station that is not higher than j (for backward assignments)
        for k in range(num_stations):
            for h in range(num_stations):
                if k <= h:
                    clauses.append([-variables[i][k][1], -variables[j][h][1]])
        # Additional Mixed constraint: disallow task i (backward) and task j (forward)
        for k in range(num_stations):
            for h in range(num_stations):
                clauses.append([-variables[i][k][1], -variables[j][h][0]])
    
    # --- Cycle Time Constraint ---
    # Introduce auxiliary variables: y[i][k] is true if task i is assigned to station k (in either mode)
    offset = num_tasks * num_stations * 2  # current highest variable number
    y_vars = [[offset + i * num_stations + k + 1 for k in range(num_stations)]
              for i in range(num_tasks)]
    
    # Linking clauses: y[i][k] <-> (X_{i,k} or W_{i,k})
    for i in range(num_tasks):
        for k in range(num_stations):
            Xik, Wik = variables[i][k][0], variables[i][k][1]
            yik = y_vars[i][k]
            # y -> (X or W): (¬yik ∨ Xik ∨ Wik)
            clauses.append([-yik, Xik, Wik])
            # X -> y: (¬Xik ∨ yik)
            clauses.append([-Xik, yik])
            # W -> y: (¬Wik ∨ yik)
            clauses.append([-Wik, yik])
    
    # For each station, encode the weighted sum constraint using our recursive approach.
    for k in range(num_stations):
        # Get the list of auxiliary variables for station k:
        y_vars_station = [y_vars[i][k] for i in range(num_tasks)]
        # Recursively encode subsets that exceed cycle_time.
        encode_cycle_time_rec(y_vars_station, tasks, cycle_time, 0, [], 0, clauses)
    
    return clauses

def solver_thread(solver, result_container):
    if solver.solve():
        result_container['model'] = solver.get_model()
    else:
        result_container['model'] = None

def solve_ualbp(num_tasks, num_stations, tasks, precedences, cycle_time):
    variables = generate_ualbp_variables(num_tasks, num_stations)
    print("Variables generated:", variables, flush=True)
    clauses = generate_ualbp_clauses(num_tasks, num_stations, tasks, precedences, cycle_time, variables)
    
    solver = Glucose3()
    for clause in clauses:
        solver.add_clause(clause)
    
    result_container = {}
    t = threading.Thread(target=solver_thread, args=(solver, result_container))
    t.start()
    
    while t.is_alive():
        print("Solver is still working...", flush=True)
        time.sleep(5)
    
    t.join()
    
    model = result_container.get('model', None)
    if model is not None:
        print("Model found:", model, flush=True)
        solution = [[] for _ in range(num_stations)]
        for i in range(num_tasks):
            for k in range(num_stations):
                if model[variables[i][k][0] - 1] > 0:
                    solution[k].append(f"{i}F")
                elif model[variables[i][k][1] - 1] > 0:
                    solution[k].append(f"{i}B")
        return solution
    else:
        return None

def print_ualbp_solution(solution):
    if solution is None:
        print("No solution found.", flush=True)
    else:
        for i, station in enumerate(solution):
            print(f"Station {i + 1}: {' '.join(str(task) for task in station)}", flush=True)

file_path = "dataset/HESKIA.IN2" 
num_tasks, tasks, precedences = read_ualbp_file(file_path)
cycle_time = 216
num_stations = 5

solution = solve_ualbp(num_tasks, num_stations, tasks, precedences, cycle_time)
print_ualbp_solution(solution)
