from pysat.solvers import Glucose3

def generate_ualbp_variables(num_tasks, num_stations):
    """ Generate variables for forward and backward assignments """
    return [[(i * num_stations * 2 + k + 1, i * num_stations * 2 + num_stations + k + 1) 
             for k in range(num_stations)] for i in range(num_tasks)]

def generate_ualbp_clauses(num_tasks, num_stations, tasks, precedences, cycle_time, variables):
    clauses = []
    
    # Task assignment constraints: Each task must be assigned exactly once (either forward or backward)
    for i in range(num_tasks):
        clauses.append([variables[i][k][0] for k in range(num_stations)] +  # Forward
                       [variables[i][k][1] for k in range(num_stations)])   # Backward
        
        # No double assignments in same station
        for k in range(num_stations):
            clauses.append([-variables[i][k][0], -variables[i][k][1]])  # Cannot be both forward and backward
        
        # Ensure task is assigned only once
        for k1 in range(num_stations):
            for k2 in range(k1 + 1, num_stations):
                clauses.append([-variables[i][k1][0], -variables[i][k2][0]])  # Forward uniqueness
                clauses.append([-variables[i][k1][1], -variables[i][k2][1]])  # Backward uniqueness
    
    # Precedence Constraints (i must be scheduled before j)
    for i, j in precedences:
        for k in range(num_stations - 1):  
            # Ensure that j is scheduled in a later station than i
            clauses.append([-variables[j][k + 1][0], variables[i][k][0]])  # Forward
            clauses.append([-variables[j][k + 1][1], variables[i][k][1]])  # Backward
    
   
    return clauses

def solve_ualbp(num_tasks, num_stations, tasks, precedences, cycle_time):
    """ Solves the UALBP-1 problem using Glucose3 SAT solver """
    variables = generate_ualbp_variables(num_tasks, num_stations)
    print(variables)
    clauses = generate_ualbp_clauses(num_tasks, num_stations, tasks, precedences, cycle_time, variables)
    
    solver = Glucose3()
    for clause in clauses:
        solver.add_clause(clause)
    
    if solver.solve():
        model = solver.get_model()
        # model=[-1, -2, -3, -4, -5, -6, -7, 8, -9, -10, -11, -12, -13, 14, -15, -16, -17, -18, -19, -20, 21, -22, -23, -24, -25, -26, -27, -28, -29, -30, 31, -32, -33, -34, -35, -36, -37, -38, -39, -40, 41, -42, -43, -44, -45, -46, -47, -48, -49, -50, -51, 52, -53, -54, -55, -56, -57, -58, -59, -60, 61, -62, -63, -64, -65, -66, -67, -68, -69, -70, 71, -72, -73, -74, -75, -76, -77, -78, -79, -80]
        print(model)
        solution = [[] for _ in range(num_stations)]
        for i in range(num_tasks):
            for k in range(num_stations):
                if model[variables[i][k][0] - 1] > 0:
                    solution[k].append(f"{i}F")  # Forward
                elif model[variables[i][k][1] - 1] > 0:
                    solution[k].append(f"{i}B")  # Backward
        return solution
    else:
        return None

def print_ualbp_solution(solution):
    """ Prints the UALBP solution in a readable format """
    if solution is None:
        print("No solution found.")
    else:
        for i, station in enumerate(solution):
            print(f"Station {i + 1}: {' '.join(str(task) for task in station)}")

# Example usage
tasks = [11, 17, 9, 5, 8, 12, 10, 3]
# precedences = [(0, 1), (1, 2), (1, 3), (2, 4), (2, 5), (3, 5), (4, 6), (5, 7)]
precedences = [(1, 0), (1, 2), (1, 3), (2, 4), (2, 5), (3, 5), (4, 6), (5, 7)]
num_tasks = len(tasks)
num_stations = 5
cycle_time = 20

solution = solve_ualbp(num_tasks, num_stations, tasks, precedences, cycle_time)
print_ualbp_solution(solution)
