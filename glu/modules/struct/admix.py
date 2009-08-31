# -*- coding: utf-8 -*-

from __future__ import division

__gluindex__  = True
__abstract__  = 'Estimate genetic admixture proportions from series of assumed ancestral populations'
__copyright__ = 'Copyright (c) 2009, BioInformed LLC and the U.S. Department of Health & Human Services. Funded by NCI under Contract N01-CO-12400.'
__license__   = 'See GLU license for terms by running: glu license'
__revision__  = '$Id$'


import sys
import time

import numpy as np
import scipy.optimize

from   itertools                 import izip
from   functools                 import partial
from   operator                  import itemgetter
from   collections               import defaultdict

from   glu.lib.fileutils         import table_reader, table_writer, \
                                        parse_augmented_filename
from   glu.lib.genolib           import load_genostream, geno_options
from   glu.lib.genolib.genoarray import genotype_count_matrix, genotype_indices


# Set absolute and relative tolerances for solutions
EPSILON=np.finfo(float).eps
ABSTOL=1e-6
RELTOL=1e-9


def normalize(x):
  '''
  Normalize an admixture vector x that may have been perturbed by roundoff
  error, truncation, or other bad things that may result in boundary
  violations.

  Steps:
    1. Clip all values to between [0..1] (inclusive)
    2. Normalize values to sum to 1 by division by x.sum()
    3. Check for round-off error and adjust 1-ULP<= x.sum() <= 1.

  N.B. x cannot have large deviations from the expected bounds or else the
       results will be rather arbitrary.
  '''
  x = np.clip(x,0,1)
  x = x/x.sum()
  while x.sum()>1:
    x /= 1+EPSILON
  return x


def admixture_lnL(f,x):
  '''
  Let F be a (n x k) matrix of known frequencies of n events from k
  distributions.  We wish to compute the negative log-likelihood function
  over a (k x 1) vector x of proportions:

    -lnL(x) = -sum(ln(F*x))

    subject to sum(x) <= 1
               min(x) >= 0

  This routine is not for use as an objective function for optimization
  algorithms.  During optimization, it is occasionally necessary to traverse
  the likelihood surface in ways that (temporarily) violate model
  constraints.
  '''
  k = f.shape[1]
  x = np.asarray(x)

  # Check bounds
  if x.min() < 0.0 or x.max() > 1.0:
    return np.inf

  s = x.sum()
  if s-1>EPSILON or s<0:
    return np.inf

  if (~np.isfinite(x)).any():
    return np.inf

  # Augment parameters
  if len(x)+1==k:
    x = np.append(x, [1-s])

  # Compute weighted mixture of likelihoods per locus
  return -np.log(np.dot(f,x)).sum()


def estimate_admixture_em(f,x0=None,iters=100):
  '''
  Problem: Maximize a likelihood to determine mixing proportions a series of
  events from a series of k Bernoulli distributions (a simplification of a
  binomial mixture problem)

  Let F be a (n x k) matrix of known frequencies of n events from k
  distributions.  We wish to maximize the following log-likelihood function
  over a (k x 1) vector x of proportions:

    lnL(x) = sum(ln(F*x))

    subject to sum(x) <= 1
               min(x) >= 0

  Note: n is typically 10,000-20,000
        k is typically 2..5

  The classical EM algorithm is used to estimate x.  It is _extremely_ slow
  to converge and is better suited for finding the neighborhood of the
  solution, rather than for precisely estimating the coefficients.  Thus we
  iterate a fixed number of times and do not bother checking for
  convergence.  Those estimates can then be used as a feasible starting
  point for algorithms with better local convergence properties.
  '''
  n,k = f.shape

  if x0 is None:
    x = np.ones((k,))/k
  else:
    # Ensure we copy, since iterations update x in place
    x = np.array(x0)

  for i in xrange(iters):
    u  = np.dot(f,x)[:,np.newaxis]
    x *= (f/u).sum(axis=0)/n

  return x


def estimate_admixture_powell(f, x0, em_factor=20):
  '''
  Problem: Maximize a likelihood to determine mixing proportions a series of
  events from a series of k Bernoulli distributions (a simplification of a
  binomial mixture problem)

  Let F be a (n x k) matrix of known frequencies of n events from k
  distributions.  We wish to maximize the following log-likelihood function
  over a (k x 1) vector x of proportions:

    lnL(x) = sum(ln(F*x))

    subject to sum(x) <= 1
               min(x) >= 0

  Note: n is typically 10,000-20,000
        k is typically 2..5

  Powell's conjugate-gradient descent method is used to estimate admixture,
  though it is an unconstrained method.  A reduced parameter space x[:-1] is
  used to partially avoid constraint violations, though good initial
  parameter estimates are required for convergence.

  This algorithm is extremely naive and is included only as a reference
  point for more sophisticated methods.
  '''
  n,k = f.shape

  iters = [0]

  # Since Powell's method is operating without knowledge of constraints,
  # begin with em_factor*k EM steps to ensure the Powell steps begin close
  # to the likelihood's maximum.
  x1 = normalize(estimate_admixture_em(f,x0=x0,iters=em_factor*k))

  # likelihood function removing the dependent parameter and optimizing on
  # the reduced parameter space of x[:-1]
  def lnL(x):
    iters[0] += 1
    x = np.asarray(x)

    # Check bounds, since Powell's method doesn't know about them
    if x.min() < 0.0 or x.max() > 1:
      return np.inf

    s = x.sum()
    if s-1>ABSTOL or s<0:
      return np.inf

    if (~np.isfinite(x)).any():
      return np.inf

    # Augment parameters
    if len(x)+1==k:
      x = np.append(x, [1-s])

    # Compute weighted mixture of likelihoods per locus
    return -np.log(np.dot(f,x)).sum()

  # Refine using Powell's conjugate-gradient descent using a reduced
  # paramter space, hopefully away from a bound.
  x = scipy.optimize.fmin_powell(lnL, x1[:-1], disp=0, ftol=RELTOL)
  x = np.append(x, [1-x.sum()])

  return x,lnL(x),iters[0]


def estimate_admixture_cvxopt(f, x0, maxiters=25, failover=True):
  '''
  Problem: Maximize a likelihood to determine mixing proportions a series of
  events from a series of k Bernoulli distributions (a simplification of a
  binomial mixture problem)

  Let F be a (n x k) matrix of known frequencies of n events from k
  distributions.  We wish to maximize the following log-likelihood function
  over a (k x 1) vector x of proportions:

    lnL(x) = sum(ln(F*x))

    subject to sum(x) <= 1
               min(x) >= 0

  Note: n is typically 10,000-20,000
        k is typically 2..5

  The CVXOPT NLP solver is used.  It is based on an interior point method
  that solves both the primary constrained problem and its dual by solving
  the KKT system of equations at every iteration.  The algorithm uses
  analytical first and second derivatives and is implemented in mostly
  Python code, so it is also relatively slow.

  Note: The solver will attempt to evaluate the likelihood and its
  derivatives at infeasible points and for the same values repeatedly.
  Also, it uses a custom matrix type that is generally less useful than the
  NumPy versions.
  '''
  # WARNING: This code mixes NumPy and CVXOPT data types.  Proceed with caution.
  from cvxopt import solvers, matrix, spdiag, mul, div, log

  n,k = f.shape
  x0  = matrix(x0)

  # Precompute cross-products of population frequencies (columns of f) for the Hessian
  ff = [ [ f[:,i][:,np.newaxis]*f[:,j][:,np.newaxis] if i>=j else 0 for j in range(k) ]
                                                                    for i in range(k) ]

  # Store last function values, since the solver seems to want to
  # re-evaluate them several times
  last   = []
  iters  = [0]

  # Build likelihood function
  def lnL(x=None, z=None):
    # Return number of non-linear constraints and initial parameters
    if x is None:
      return 0,x0

    # Do not check constraints or else optimization will often get "stuck"
    x = np.asarray(x, dtype=float)

    # Check to see if we've just solved this case
    if last:
      d = (abs(x-last[0])).sum()
      if d==0:
        last_x,last_z,last_l,last_df,last_h = last
        if z is None:
          return last_l,last_df
        elif z[0]==last_z:
          return last_l,last_df,last_h

    iters[0] += 1

    # Compute mixture probabilities and log-likelihood
    u  =  np.dot(f,x)
    l  = -np.log(u).sum()

    if not np.isfinite(l):
      return None

    # Compute derivatives
    df = matrix( -(f/u).sum(axis=0), tc='d').T

    if z is None:
      last[:] = [x+0,None,l,df,None]
      return l,df

    # Compute Hessian, if requested
    u2 = u**2
    h  = matrix([ [ z[0]*(ff[i][j]/u2).sum() if i>=j else 0 for i in range(k) ]
                                                            for j in range(k) ], tc='d')

    last[:] = [x+0,z[0],l,df,h]
    return l,df,h

  # Set up constraint matrices
  #   k inequality constaints for x[i]>=0
  G = matrix([ [0.]*i + [-1.] + [0]*(k-i-1) for i in range(k) ]).T
  h = matrix([0.]*k)

  #   1 equality constraint for sum(x)==1
  A = matrix(np.ones(k)).T
  b = matrix(np.ones(1))

  # Set solver options
  solvers.options['show_progress'] = False
  solvers.options['maxiters']      = maxiters
  solvers.options['abstol']        = ABSTOL
  solvers.options['reltol']        = RELTOL

  # Run solver
  sol = solvers.cp(lnL, G, h, A=A, b=b)

  # Return results (paramters, number of iterations, final log-likelihood)
  x = np.asarray(sol['x'])
  l = lnL(x)[0]

  # Allow algorithm to fail and re-try problem with SQP (without
  # recursive failover)
  if sol['status'] != 'optimal' and failover:
    x2,l2,iters2 = estimate_admixture_sqp(f, x0, failover=False)
    iters[0] += iters2

    if l2<l:
      x,l=x2,l2

  return x,l,iters[0]


def estimate_admixture_openopt(f, x0, method='ralg'):
  '''
  Problem: Maximize a likelihood to determine mixing proportions a series of
  events from a series of k Bernoulli distributions (a simplification of a
  binomial mixture problem)

  Let F be a (n x k) matrix of known frequencies of n events from k
  distributions.  We wish to maximize the following log-likelihood function
  over a (k x 1) vector x of proportions:

    lnL(x) = sum(ln(F*x))

    subject to sum(x) <= 1
               min(x) >= 0

  Note: n is typically 10,000-20,000
        k is typically 2..5

  OPENOPT's ralg algorithm is used, which is a constrained NLP/NSP solver
  written by Dmitrey Kroshko.
  '''
  from openopt import NLP

  n,k = f.shape

  # Precompute cross-products of population frequencies (columns of f) for the Hessian
  ff = [ [ f[:,i][:,np.newaxis]*f[:,j][:,np.newaxis] for j in range(k) ]
                                                     for i in range(k) ]

  # Store last function values, since the solver seems to want to
  # re-evaluate them several times
  last   = []
  iters  = [0]

  sqp = method=='scipy_slsqp'

  # Build likelihood function
  def lnL(x):
    # Do not check constraints or else optimization will often get "stuck"
    iters[0] += 1

    # Compute mixture probabilities and log-likelihood
    u =  np.dot(f,x)
    l = -np.log(u).sum()

    if sqp and not np.isfinite(l):
      return np.inf

    return l

  def dlnL(x):
    # Compute derivatives
    u  =  np.dot(f,x)[:,np.newaxis]
    df = -(f/u).sum(axis=0)
    return df

  def d2lnL(x):
    u2 =  np.dot(f,x)**2
    h  = np.array([ [ (ff[i][j]/u2).sum() for i in range(k) ]
                                          for j in range(k) ], dtype=float)
    return h

  #   1 equality constraint for sum(x)==1
  A = np.ones(k)
  b = np.ones(1)

  p = NLP(f=lnL, df=dlnL, x0=x0, lb=np.zeros(k), ub=np.ones(k), Aeq=A, beq=b, d2f=d2lnL,
          maxIter=10000, iprint=-1, ftol=ABSTOL, xtol=ABSTOL)

  r = p.solve(method)

  return r.xf,r.ff,iters[0]


def estimate_admixture_sqp(f, x0, failover=True):
  '''
  Problem: Maximize a likelihood to determine mixing proportions a series of events from a
  series of k Bernoulli distributions (a simplification of a binomial mixture problem)

  Let F be a (n x k) matrix of known frequencies of n events from k
  distributions.  We wish to maximize the following log-likelihood function
  over a (k x 1) vector x of proportions:

    lnL(x) = sum(ln(F*x))

    subject to sum(x) <= 1
               min(x) >= 0

  Note: n is typically 10,000-20,000
        k is typically 2..5

  Estimation is by the Sequential Quadratic Programming algorithm as
  implemented in SciPy, which is based on the Sequential Least SQuares
  Programming optimization algorithm (SLSQP), originally developed by Dieter
  Kraft.  See http://www.netlib.org/toms/733
  '''
  from scipy.optimize import fmin_slsqp

  n,k = f.shape
  x0 = np.array(x0)

  # Precompute cross-products of population frequencies (columns of f) for the Hessian
  ff = [ [ f[:,i][:,np.newaxis]*f[:,j][:,np.newaxis] if i>=j else 0 for j in range(k) ]
                                                                    for i in range(k) ]

  # Store last function values, since the solver seems to want to
  # re-evaluate them several times
  last  = []
  iters = [0]

  # Build likelihood function
  def lnL(x):
    # Do not check constraints or else optimization will often get "stuck"
    iters[0] += 1

    u =  np.dot(f,x)
    l = -np.log(u).sum()

    if not np.isfinite(l):
      return np.inf

    last[:] = np.array(x),u[:,np.newaxis]
    return l

  def dlnL(x):
    # Compute derivatives
    if np.abs(x-last[0]).sum()==0:
      u = last[1]
    else:
      u = np.dot(f,x)[:,np.newaxis]

    return -(f/u).sum(axis=0)

  # Define equality constraints and derivatives
  # Weight norms since that seems to push estimates away from bounds (should
  # be much larger than the norm of the log likelihood)
  w = 1e4**k
  eq = np.ones(1)
  def eqcons(x):
    eq[0] = w*(x.sum()-1)
    return eq

  deq = np.ones( (1,k) )*w
  def fprime_eqcons(x):
    return deq

  x,fx,its,imode,smode = fmin_slsqp(lnL, fprime=dlnL, x0=x0, bounds=[(0,1)]*k,
                                    f_eqcons=eqcons, fprime_eqcons=fprime_eqcons,
                                    iter=25, full_output=True, iprint=-1, acc=ABSTOL/10)

  x = np.asarray(x)

  # Allow algorithm to fail and re-try problem with CVXOPT (without
  # recursive failover)
  if imode != 0 and failover:
    # Unless iteration limit was exceeded, start from the initial parameters
    x1 = x if imode == 9 else x0

    x2,fx2,iters2 = estimate_admixture_cvxopt(f, x1, failover=False)
    iters[0] += iters2

    if fx2<fx:
      x=x2

  x = np.clip(x,0,1)
  return x,fx,iters[0]


def classify_ancestry(labels,x,threshold):
  '''
  An individual is considered of a given ancestry based on the supplied
  labels and estimated admixture coefficients if their coefficient is
  greater than a given threshold.

  Otherwise, an individual who has no single estimated admixture coefficient
  that meets the specified threshold then one of two behaviors result.  If
  only one population group exceeds 1-threshold then the ancestry is deemed
  'ADMIXED' for that population.  Otherwise, a list of populations with
  estimated admixture above 1-threshold is returned.
  '''
  popset = set()

  cmax = -1
  for pop,coeff in izip(labels,x):
    if coeff >= 1-threshold:
      popset.add(pop)
      cmax = max(cmax,coeff)

  if len(popset)==1 and cmax < threshold:
    ipop = 'ADMIXED %s' % popset.pop()
  else:
    ipop = ','.join(sorted(popset))

  return ipop


def progress_bar(samples, sample_count):
  try:
    from glu.lib.progressbar import progress_loop
  except ImportError:
    return samples

  update_interval = max(1,min(sample_count//100,250))

  return progress_loop(samples, length=sample_count, units='samples', update_interval=update_interval)


def load(options,args):
  # Load samples to test
  sys.stderr.write('Loading %s...\n' % args[0])
  test = load_genostream(args[0],format=options.informat,genorepr=options.ingenorepr,
                                 genome=options.loci,phenome=options.pedigree,
                                 transform=options, hyphen=sys.stdin).as_sdat()

  # Initialize masks
  loci = test.loci
  locusset = set(test.loci)

  # Load source populations, align loci, and compute frequencies

  pops = []
  for arg in args[1:]:
    sys.stderr.write('Loading %s...\n' % arg)
    genos = load_genostream(arg,format=options.informat,genorepr=options.ingenorepr,
                                genome=test.genome,phenome=options.pedigree,
                                transform=options,includeloci=locusset,orderloci=loci)

    # Count genotypes
    pop_loci,samples,geno_counts = genotype_count_matrix(genos)

    # Update masks
    locusset &= set(pop_loci)
    loci = [ l for l in loci if l in locusset ]
    mask = np.array([ l in locusset for l in pop_loci ],dtype=bool)
    geno_counts = geno_counts[mask]

    # Set missing genotypes to zero
    geno_counts[:,0] = 0

    if options.model.upper() == 'GENO':
      # Set each genotype to be observed at least once
      np.clip(geno_counts,1,1e300,out=geno_counts)
      geno_counts[:,0] = 0

      # Compute frequencies
      n = geno_counts.sum(axis=1)[:,np.newaxis]
      geno_freqs = geno_counts/n

    elif options.model.upper() == 'HWP':
      geno_freqs = np.zeros(geno_counts.shape, dtype=float)

      for i,model in enumerate(genos.models):
        n = 2*geno_counts[i].sum()

        if not n or len(model.alleles)!=3:
          p = 1/len(genos.samples)
        else:
          a,b  =  model.alleles[1:3]
          inds = (model[a,a].index,
                  model[a,b].index,
                  model[b,b].index)

          hom1 = geno_counts[i,inds[0]]
          hets = geno_counts[i,inds[1]]
          hom2 = geno_counts[i,inds[2]]

          p    = (2*hom1+hets)/n

        q = 1-p

        geno_freqs[i,inds[0]] =   p*p
        geno_freqs[i,inds[1]] = 2*p*q
        geno_freqs[i,inds[2]] =   q*q
    else:
      raise ValueError('Invalid genotype likelihood model specified: %s' % options.model)

    # Append to list of source populations
    pops.append( (pop_loci,geno_freqs) )

  # Perform final mask of individual data
  test = test.transformed(includeloci=loci)

  # Perform final mask of frequency data
  for i,(pop_loci,geno_freqs) in enumerate(pops):
    mask = np.array([ (l in locusset) for l in pop_loci ], dtype=bool)
    pops[i] = geno_freqs[mask]

  return test,pops


def build_labels(options,args):
  k = len(args)-1

  labels = []
  for label in options.labels:
    labels.extend( l.strip() for l in label.split(',') )

  if '' in labels:
    raise ValueError('Blank population label specified')

  if len(labels) != len(set(labels)):
    raise ValueError('Duplicate population label specified')

  if len(labels) > len(args)-1:
    raise ValueError('Too many population labels specified')

  while len(labels) < k:
    labels.append('POP%d' % (len(labels)+1))

  return labels


def load_references(filenames,k):
  refs = []

  expected_len = k+1

  for filename in filenames:
    args = {}
    filename = parse_augmented_filename(filename,args)
    name = args.pop('name',filename)
    data = table_reader(filename, want_header=True, **args)
    header = data.next()

    if len(header) < expected_len:
      raise ValueError('Too few columns in reference file %s (saw %d, expected at least %d'
                        % (filename,len(header),expected_len))

    data = dict( (row[0],map(float,row[1:expected_len])) for row in data )

    refs.append( (name,data) )

  return refs


def option_parser():
  import optparse

  usage = 'usage: %prog [options] test_genotypes pop1_genotypes pop2_genotypes [pop3_genotypes...]'
  parser = optparse.OptionParser(usage=usage)

  geno_options(parser,input=True,filter=True)

  parser.add_option('--labels', dest='labels', metavar='LABELS', action='append', default=[],
                    help='Population labels (specify one per population separated with commas)')
  parser.add_option('--model', dest='model', metavar='MODEL', default='HWP',
                    help='Model for genotype frequencies.  HWP to assume Hardy-Weinberg proportions, '
                         'otherwise GENO to fit genotypes based on frequency.  (Default=HWP)')
  parser.add_option('--reference', dest='reference', metavar='FILE', action='append', default=[],
                    help='Compare results to another struct.admix output file')
  parser.add_option('-t', '--threshold', dest='threshold', metavar='N', type='float', default=0.80,
                    help='Imputed ancestry threshold (default=0.80)')
  parser.add_option('-o', '--output', dest='output', metavar='FILE', default='-',
                    help='output table file name')
  parser.add_option('-P', '--progress', dest='progress', action='store_true',
                    help='Show analysis progress bar, if possible')

  return parser


def main():
  parser = option_parser()
  options,args = parser.parse_args()

  if len(args) < 2:
    parser.print_help()
    sys.exit(2)

  # Build population labels
  labels    = build_labels(options,args)
  test,pops = load(options,args)

  k = len(pops)
  n = len(test.samples)

  refs = load_references(options.reference,k)

  out = table_writer(options.output,hyphen=sys.stdout)
  out.writerow(['SAMPLE']+labels+['IMPUTED_ANCESTRY'])

  methods = [ ('SQP',      estimate_admixture_sqp),
#             ('POWELL10', partial(estimate_admixture_powell,  em_factor=10)),
#             ('POWELL25', partial(estimate_admixture_powell,  em_factor=25)),
#             ('POWELL50', partial(estimate_admixture_powell,  em_factor=50)),
#             ('RALG',     partial(estimate_admixture_openopt, method='ralg')),
#             ('OOSQP',    partial(estimate_admixture_openopt, method='scipy_slsqp')),
#             ('CVXOPT',   estimate_admixture_cvxopt),
            ]

  times  = defaultdict(int)
  iters  = defaultdict(int)
  scores = defaultdict(float)

  # Internal option for testing
  outputsummary = False

  def summary(i):
    if not outputsummary:
      return

    # Produce summary performance table
    total = sum(times.itervalues())

    results = [ (method,scores[method],t,iters[method]) for method,t in times.iteritems() ]
    results.sort(key=itemgetter(1,2,0))

    out.writerow(['SUMMARY','SAMPLE=%d' % i])
    out.writerow(['METHOD','SCORE','ITERS','TIME','%TIME','ITER/SEC','SAMPLE/SEC'])
    for method,score,t,it in results:
      ti = (it/t) if t else 0
      ts = (i/t)  if t else 0
      out.writerow([method, '%0.2f' % score, it, '%.2f' % t,'%.2f' % (t/total*100),
                            '%.3f' % ti,'%.3f' % ts])

    out.writerow([])

  if options.progress and test.samples:
    test = progress_bar(test, len(test.samples))

  for i,(sample,genos) in enumerate(test):
    if i%250==0 and i:
      summary(i)

    t0 = time.clock()
    # Compute genotype frequencies, f
    ind     = np.asarray(genotype_indices(genos), dtype=int)
    mask    = ind>0
    indices = np.arange(len(ind))
    f       = np.array([ pop[indices,ind][mask] for pop in pops ], dtype=float).T

    # Find feasible starting values
    x0      = normalize(estimate_admixture_em(f,iters=0*k))
    times['PREP'] += time.clock()-t0

    # Optimize using each method selected
    results = []
    for method,optfunc in methods:
      t0 = time.clock()
      x,fx,it = optfunc(f, x0)
      times[method] += time.clock()-t0
      iters[method] += it
      x = normalize(x)
      ipop = classify_ancestry(labels, x, options.threshold)
      results.append([method] + ['%.4f' % a for a in x] + [ipop, it, fx])

    # Provide reference results, if available
    for name,data in refs:
      if sample in data:
        times[name] = 0
        x = normalize(data[sample])
        ipop = classify_ancestry(labels, x, options.threshold)
        results.append([name] + ['%.4f' % a for a in x] + [ipop, '', admixture_lnL(f,x), ])


    if len(results) == 1:
      results[0][0] = sample
      out.writerow(results[0][:-1])
    else:
      # Show results sorted by -log-likelihood (descending)
      results.sort(key=itemgetter(k+3,k+2,0))

      for r in results:
        # Bake-off code
        if 0:
          s = r[k+3] - results[0][k+3]
          scores[r[0]] += s if np.isfinite(s) else 10
          r.append('%.2f' % s)
        else:
          r = r[:-1]

        r[0] = '   %s   ' % r[0]

      out.writerow([sample])
      out.writerows(results)
      out.writerow([])

  summary(n)


if __name__=='__main__':
  main()