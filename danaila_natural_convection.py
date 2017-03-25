'''

    @brief  Solve the benchmark "differentially heated cavity" natural convection problem using finite elements.

    @detail
        
        Solve the natural convection test problem from

            @article
            {danaila2014newton,
              title={A Newton method with adaptive finite elements for solving phase-change problems with natural convection},
              author={Danaila, Ionut and Moglan, Raluca and Hecht, Fr{\'e}d{\'e}ric and Le Masson, St{\'e}phane},
              journal={Journal of Computational Physics},
              volume={274},
              pages={826--840},
              year={2014},
              publisher={Academic Press}
            }
        
        Match the notation in danaila2014newton as best as possible.

    
    @author Alexander G. Zimmerman <zimmerman@aices.rwth-aachen.de>
    
'''

from fenics import \
    UnitSquareMesh, FiniteElement, VectorElement, MixedElement, \
    FunctionSpace, VectorFunctionSpace, \
    Function, TrialFunction, TestFunctions, split, \
    DirichletBC, Constant, Expression, \
    dx, \
    dot, inner, grad, sym, div, \
    errornorm, norm, \
    File, \
    Progress, set_log_level, PROGRESS, \
    project, interpolate, \
    solve

    
# Set physical parameters
Ra = 1.e6

Pr = 0.71

Re = 1.

theta_h = 0.5

theta_c = -0.5

K = 1.

g = (0., -1.)

mu = 1.


# Set other parameters

final_time = 1.e-5

num_time_steps = 2

gamma = 1.e-7

global_mesh_bisection_levels = 4

pressure_order = 1

temperature_order = 1

linearize = False

if linearize:

    max_newton_iterations = 50


# Compute derived parameters
time_step_size = final_time / num_time_steps

velocity_order = pressure_order + 1

tolerance = 0.1*gamma

# Create mesh
nc = 2**global_mesh_bisection_levels

mesh = UnitSquareMesh(nc, nc)


# Define function spaces for the system
VxV = VectorFunctionSpace(mesh, 'Lagrange', velocity_order)

Q = FunctionSpace(mesh, 'Lagrange', pressure_order)

V = FunctionSpace(mesh, 'Lagrange', temperature_order)

'''
MixedFunctionSpace used to be available but is now deprecated. 
The way that fenics separates function spaces and elements is confusing.
To create the mixed space, I'm using the approach from https://fenicsproject.org/qa/11983/mixedfunctionspace-in-2016-2-0
'''
VxV_ele = VectorElement('Lagrange', mesh.ufl_cell(), velocity_order)

Q_ele = FiniteElement('Lagrange', mesh.ufl_cell(), pressure_order)

V_ele = FiniteElement('Lagrange', mesh.ufl_cell(), temperature_order)

W = FunctionSpace(mesh, MixedElement([VxV_ele, Q_ele, V_ele]))


# Define function and test functions
w = Function(W)

w_n = Function(W)

if linearize:

    w_k = Function(W)
    
    w_w = TrialFunction(W)
   

v, q, phi = TestFunctions(W)

    
# Split solution function to access variables separately
u, p, theta = split(w)

u_n, p_n, theta_n = split(w_n)

if linearize:

    u_k, p_k, theta_k = split(w_k)
    
    u_w, p_w, theta_w = split(w_w)
    

# Define boundaries
hot_wall = 'near(x[0],  0.)'

cold_wall = 'near(x[0],  1.)'

adiabatic_walls = 'near(x[1],  0.) | near(x[1],  1.)'

# Define boundary conditions
if linearize:

    def boundary(x, on_boundary):
        return on_boundary
        
    bc = DirichletBC(W, Constant((0., 0., 0., 0.)), boundary)

else:

    bc = [ \
        DirichletBC(W, Constant((0., 0., 0., theta_h)), hot_wall), \
        DirichletBC(W, Constant((0., 0., 0., theta_c)), cold_wall), \
        DirichletBC(W.sub(0), Constant((0., 0.)), adiabatic_walls), \
        DirichletBC(W.sub(1), Constant((0.)), adiabatic_walls)]
    
    
# If formulating the Newton linearzed system, then we must specify the initial values
if linearize:
    u_n = interpolate(Constant((0., 0.)), VxV)
    
    p_n = interpolate(Constant(0.), Q)
    
    theta_iv_exp = Expression(str(theta_h) + ' + x[0]*(' + str(theta_c) + ' - ' + str(theta_h) + ')', \
        
        degree=temperature_order)
        
    theta_n = interpolate(theta_iv_exp, V)
    

# Define expressions needed for variational format
Ra = Constant(Ra)

Pr = Constant(Pr)

Re = Constant(Re)

K = Constant(K)

mu = Constant(mu)

g = Constant(g)

dt = Constant(time_step_size)

gamma = Constant(gamma)


# Define variational form
def f_B(_theta):
    
    return _theta*Ra/(Pr*Re*Re)*g
       
   
def a(_mu, _u, _v):

    def D(_u):
    
        return sym(grad(_u))
    
    return 2.*_mu*inner(D(_u), D(_v))
    

def b(_u, _q):
    
    return -div(_u)*_q
    

def c(_w, _z, _v):
    
    return dot(div(_w)*_z, _v)
    
    
if linearize: # Implement the Newton linearized form published in danaila2014newton

    df_B_dtheta = Ra/(Pr*Re*Re)*g
    
    A = (\
        b(u_w,q) - gamma*p_w*q \
        + dot(u_w, v)/dt + c(u_w, u_k, v) + c(u_k, u_w, v) + a(mu, u_w, v) + b(v, p_w) \
        - dot(theta_w*df_B_dtheta, v) \
        + theta_w*phi/dt - dot(u_k, grad(phi))*theta_w - dot(u_w, grad(phi))*theta_k + dot(K/Pr*grad(theta_w), grad(phi)) \
        )*dx
        
    L = (\
        b(u_k,q) + gamma*p_k*q \
        + dot(u_k - u_n, v)/dt + c(u_k, u_k, v) + a(mu, u_k, v) + b(v, p_k) - dot(f_B(theta_k), v) \
        + (theta_k - theta_n)*phi/dt - dot(u_k, grad(phi))*theta_k - dot(K/Pr*grad(theta_k), grad(phi)) \
        )*dx
    
else: # Implement the nonlinear form, which will allow FEniCS to automatically derive the Newton linearized form.

    F = (\
        b(u, q) - gamma*p*q \
        + dot(u, v)/dt + c(u, u, v) + a(mu, u, v) + b(v, p) - dot(u_n, v)/dt \
        - dot(f_B(theta), v) \
        + theta*phi/dt - dot(u, grad(phi))*theta + dot(K/Pr*grad(theta), grad(phi)) - theta_n*phi/dt \
        )*dx

    
# Create VTK file for visualization output
velocity_file = File('danaila_natural_convection/velocity.pvd')

pressure_file = File('danaila_natural_convection/pressure.pvd')

temperature_file = File('danaila_natural_convection/temperature.pvd')


# Create progress bar
progress = Progress('Time-stepping')

set_log_level(PROGRESS)


# solve() requires the second argument to be a Function instead of a TrialFunction
_w_w = Function(W)

# Solve each time step

time_residual = Function(W)

for n in range(num_time_steps):

    time = n*time_step_size
    
    if linearize:
    
        print '\nIterating Newton method'
        
        converged = False
        
        iteration_count = 0
        
        for k in range(max_newton_iterations):

            solve(A == L, _w_w, bc)
            
            w_k.assign(w_k - _w_w)
            
            norm_residual = norm(_w_w, 'H1')

            print '\nH1 norm residual = ' + str(norm_residual) + '\n'
            
            if norm_residual < tolerance:
            
                converged = True
                
                iteration_count = k + 1
                
                print 'Converged after ' + str(k) + ' iterations'
                
                break
                
        assert(converged)
        
        w.assign(w_k)
            
    else:
    
        solve(F == 0, w, bc) # Solve nonlinear problem for this time step
    
    
    # Save solution to files
    _velocity, _pressure, _temperature = w.split()
    
    velocity_file << (_velocity, time) 
    
    pressure_file << (_pressure, time) 
    
    temperature_file << (_temperature, time) 
    
    # Update previous solution
    w_n.assign(w)
    
    # Show the time progress
    progress.update(time / final_time)
    