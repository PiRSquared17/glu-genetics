# -*- coding: utf-8 -*-

from __future__ import division

__abstract__  = 'Various edit distance algorithms'
__copyright__ = 'Copyright (c) 2010, BioInformed LLC and the U.S. Department of Health & Human Services. Funded by NCI under Contract N01-CO-12400.'
__license__   = 'See GLU license for terms by running: glu license'

cimport cython
cimport numpy as np

import numpy as np

from libc.stdio    cimport sprintf
from libc.stdlib   cimport malloc, realloc, calloc, free
from cpython       cimport PyString_Size, PyErr_NoMemory

from   glu.lib.utils        import namedtuple
from   glu.lib.seqlib.edits import cigar_to_string, cigar_alignment

EditOp  = namedtuple('EditOp',  'op pos old new')
CigarOp = namedtuple('CigarOp', 'op count')


cdef inline Py_ssize_t min2(Py_ssize_t a, Py_ssize_t b):
  if a < b:
    return a
  else:
    return b


cdef inline Py_ssize_t min3(Py_ssize_t a, Py_ssize_t b, Py_ssize_t c):
  return min2(min2(a,b),c)


cdef inline Py_ssize_t min4(Py_ssize_t a, Py_ssize_t b, Py_ssize_t c, Py_ssize_t d):
  return min2(min2(a,b),min2(c,d))


cdef inline Py_ssize_t max2(Py_ssize_t a, Py_ssize_t b):
  if a >= b:
    return a
  else:
    return b


cdef inline Py_ssize_t max3(Py_ssize_t a, Py_ssize_t b, Py_ssize_t c):
  return max2(max2(a,b),c)


cdef inline Py_ssize_t max4(Py_ssize_t a, Py_ssize_t b, Py_ssize_t c, Py_ssize_t d):
  return max2(max2(a,b),max2(c,d))


def hamming_distance(s1, s2):
  '''
  Calculate the Hamming distance between two sequences.

  This distance is the number of substitutions needed to transform the first
  sequence into the second.  Both sequences are required to be of equal
  length.

  See: http://en.wikipedia.org/wiki/Hamming_distance

       Hamming, Richard W. (1950), "Error detecting and error correcting
       codes", Bell System Technical Journal 26 (2): 147–160,
       http://www.ece.rutgers.edu/~bushnell/dsdwebsite/hamming.pdf

  This implementation requires O(N) time and O(1) space, where N is the
  length of the input sequences.

  >>> hamming_distance('abc', 'abc')
  0
  >>> hamming_distance('abb', 'abc')
  1
  >>> hamming_distance('abc', 'def')
  3
  >>> hamming_distance('a', 'ab')
  Traceback (most recent call last):
  ...
  ValueError: Length mismatch
  '''
  cdef Py_ssize_t d = 0
  cdef Py_ssize_t l1 = PyString_Size(s1)
  cdef Py_ssize_t l2 = PyString_Size(s2)

  if l1!=l2:
    raise ValueError('Length mismatch')

  cdef char *ss1 = s1
  cdef char *ss2 = s2

  for i in range(l1):
    if ss1[i]!=ss2[i]:
      d += 1

  return d


cdef reduce_match(s1, s2):
  '''
  Reduce matching problem size by removing any common prefix and suffix from
  s1 and s2 and returning the prefix size to adjust the edit sequence

  >>> reduce_match('xxx','yyy')
  ('xxx', 'yyy', 0)
  >>> reduce_match('abc','ac')
  ('b', '', 1)
  >>> reduce_match('abcdefg','abcxxx')
  ('defg', 'xxx', 3)
  >>> reduce_match('abcxxx','defxxx')
  ('abc', 'def', 0)
  >>> reduce_match('abc','abc')
  ('', '', 3)
  '''
  cdef Py_ssize_t l1 = PyString_Size(s1)
  cdef Py_ssize_t l2 = PyString_Size(s2)
  cdef Py_ssize_t l  = min2(l1,l2)

  cdef char *ss1 = s1
  cdef char *ss2 = s2

  cdef Py_ssize_t  i = 0, j = l1-1

  for i in range(l):
    if ss1[i]!=ss2[i]:
      break

  for j in range(l-i):
    if ss1[l1-j-1]!=ss2[l2-j-1]:
      break

  return s1[i:l1-j],s2[i:l2-j],i


def levenshtein_distance(s1, s2):
  '''
  Calculate a minimum number of edit operations to transform s1 into s2
  based on the Levenshtein distance.

  This distance is the number of insertions, deletions, and substitutions
  needed to transform the first sequence into the second.

  See: http://en.wikipedia.org/wiki/Levenshtein_distance

       В.И. Левенштейн (1965). "Двоичные коды с исправлением выпадений, вставок и
       замещений символов".  Доклады Академий Наук СCCP 163 (4): 845–8.  Appeared
       in English as: Levenshtein VI (1966).  "Binary codes capable of correcting
       deletions, insertions, and reversals".  Soviet Physics Doklady 10:
       707–10.  http://www.scribd.com/full/18654513?access_key=key-10o99fv9kcwswflz9uas

  This implementation is based on a standard dynamic programming algorithm,
  requiring O(N*M) time and O(min(N,M)) space, where N and M are the lengths
  of the two sequences.  See the following for more information on these
  concepts:

    http://en.wikipedia.org/wiki/Dynamic_programming
    http://en.wikipedia.org/wiki/Big_O_notation

  The the cost to transform s1[:i]->s2[:j] is based on the following
  recurrence:

              |  i                       if i>=0, j=0  (delete s1[:i])
              |  j                       if i =0, j>0  (insert s2[:j])
  cost[i,j] = |
              |     | cost[i-1,j-1]      if c1==c2     (match)
              | min | cost[i-1,j-1] + 1  if c1!=c2     (substitution)
              |     | cost[i,  j-1] + 1                (insert c2)
              |     | cost[i-1,j  ] + 1                (delete c1)

  where c1=s1[i-1], c2=s2[j-1].  The resulting minimum edit distance is then
  cost[i,j].  This implementation saves space by only storing the last two
  cost rows at any given time (cost[i-1], and cost[i]).

  >>> levenshtein_distance('ac', 'abc')
  1
  >>> levenshtein_distance('ba', 'ab')
  2
  >>> levenshtein_distance('eat', 'seat')
  1
  >>> levenshtein_distance('abcdefghijk','cdefghijklm')
  4
  '''
  # Reduce problem size by removing any common prefix or suffix
  s1,s2,_ = reduce_match(s1,s2)

  # Minimize storage by forcing s2 to the shorter sequence
  if len(s1) < len(s2):
    s1,s2 = s2,s1

  # Fast-path: If s2 is empty, return distance of len(s1)
  if not s2:
    return len(s1)

  cdef Py_ssize_t n = PyString_Size(s1)
  cdef Py_ssize_t m = PyString_Size(s2)

  cdef Py_ssize_t  i,j,cost,match,insert,delete

  # Otherwise, prepare storage for the edit costs
  # Only store the current and previous cost rows, adding a single
  # element to the beginning for the cost of inserting i characters

  cdef Py_ssize_t *current  = <Py_ssize_t *>calloc( (m+1), sizeof(Py_ssize_t))
  cdef Py_ssize_t *previous = <Py_ssize_t *>calloc( (m+1), sizeof(Py_ssize_t))

  # Start by assigning the cost of transforming an empty s1 into s2[0:m] by
  # inserting 0..m elements
  # Initialize previous costs to zero, since the values are not used and are
  # going to be overwritten
  for i in range(m+1):
    current[i]  = i
    previous[i] = 0

  cdef char *ss1 = s1
  cdef char *ss2 = s2
  cdef char c1,c2

  # For each location in s1
  for i in range(n):
    c1 = ss1[i]

    # Swap current and previous cost row storage to recycle the old
    # 'previous' as the new 'current'
    previous,current = current,previous

    # Initialize the cost of inserting characters up to and including i
    current[0] = i+1

    # Update minimum match, insertion, and deletion costs for each
    # location in s2
    for j in range(m):
      c2 = ss2[j]

      if c1==c2:
        cost = 0
      else:
        cost = 1

      # Compute cost of transforming s1[0:i+1]->s2[0:j+1] allowing the
      # following edit operations:

      # Match:        transform s1[0:i]->s2[0:j] + 0, if s1[i]==s2[j]
      # Substitution: transform s1[0:i]->s2[0:j] + 1, if s1[i]!=s2[j]
      match        = previous[j]   + cost

      # Insert: transform s1[0:i+1]->s2[0:j] and insert s2[j]
      insert       = current[j]    + 1

      # Delete: transform s1[0:i]->s2[0:j+1] and delete s1[i]
      delete       = previous[j+1] + 1

      # Take minimum cost operation
      current[j+1] = min3(match, insert, delete)

  # Return the minimum edit cost for both complete sequences.  i.e. the cost
  # transforming s1[0:i+1]->s2[0:j+1], which is current[-1].
  distance = current[m]

  free(current)
  free(previous)

  return distance


def damerau_levenshtein_distance(s1, s2):
  '''
  Calculate a minimum number of edit operations to transform s1 into s2
  based on the Damerau-Levenshtein distance.

  This distance is the number of insertions, deletions, substitutions, and
  transpositions needed to transform the first sequence into the second.
  Transpositions are exchanges of two *consecutive* characters and may not
  overlap with other transpositions.

  The operations required to incrementally transform s1 into s2 are returned
  as a sequence of operations, represented by tuples of the form:

    Substitution:  EditOp(op='S', pos=position, old=old,  new=new)
    Insertion:     EditOp(op='I', pos=position, old=None, new=new)
    Deletion:      EditOp(op='D', pos=position, old=old,  new=None)
    Transposition: EditOp(op='T', pos=position, old=old,  new=new)

  When compress=False, substitution, insertion, and deletions operations are
  always performed a single character or element at a time.  When
  compress=True, adjacent operations are combined into multi-character or
  multi-element operations, when possible.

  See: http://en.wikipedia.org/wiki/Damerau%E2%80%93Levenshtein_distance

       В.И. Левенштейн (1965). "Двоичные коды с исправлением выпадений, вставок и
       замещений символов".  Доклады Академий Наук СCCP 163 (4): 845–8.  Appeared
       in English as: Levenshtein VI (1966).  "Binary codes capable of correcting
       deletions, insertions, and reversals".  Soviet Physics Doklady 10:
       707–10.  http://www.scribd.com/full/18654513?access_key=key-10o99fv9kcwswflz9uas

       Damerau F (1964). "A technique for computer detection and correction
       of spelling errors".  Communications of the ACM 7 (3):171-6.
       http://www.cis.uni-muenchen.de/~heller/SuchMasch/apcadg/literatur/data/damerau_distance.pdf

  This implementation is based on a standard dynamic programming algorithm,
  requiring O(N*M) time and O(min(N,M)) space, where N and M are the lengths
  of the two sequences.  See the following for more information on these
  concepts:

    http://en.wikipedia.org/wiki/Dynamic_programming
    http://en.wikipedia.org/wiki/Big_O_notation

  The the cost to transform s1[:i]->s2[:j] is based on the following
  recurrence:

              |  i                       if i>=0, j=0  (delete s1[:i])
              |  j                       if i =0, j>0  (insert s2[:j])
              |
              |     | cost[i-1,j-1]      if c1==c2     (match)
  cost[i,j] = |     | cost[i-1,j-1] + 1  if c1!=c2     (substitution)
              |     | cost[i,  j-1] + 1                (insert c2)
              | min | cost[i-1,j  ] + 1                (delete c1)
              |     | cost[i-2,j-2] + 1  if i>1, j>1,  (transpose)
              |     |                       s1[i-2]==c2,
              |     |                       s2[j-2]==c1

  where c1=s1[i-1], c2=s2[j-1].  The resulting minimum edit distance is then
  cost[i,j].  This implementation saves space by only storing the last three
  cost rows at any given time (cost[i-2], cost[i-1], and cost[i]).

  >>> damerau_levenshtein_distance('ba', 'ab')
  1
  >>> damerau_levenshtein_distance('ba', 'abc')
  2
  >>> damerau_levenshtein_distance('fee', 'deed')
  2
  >>> damerau_levenshtein_distance('eat', 'seat')
  1
  '''
  # Reduce problem size by removing any common prefix or suffix
  s1,s2,_ = reduce_match(s1,s2)

  # Minimize storage by forcing s2 to the shorter sequence
  if len(s1) < len(s2):
    s1,s2 = s2,s1

  # Fast-path: If s2 is empty, return distance of len(s1)
  if not s1:
    return len(s2)

  # Otherwise, prepare storage for the edit costs
  # Only store the current and previous cost rows, adding a single
  # element to the beginning for the cost of inserting i characters

  cdef Py_ssize_t n = PyString_Size(s1)
  cdef Py_ssize_t m = PyString_Size(s2)

  cdef Py_ssize_t  i,j,cost,match,insert,delete,trans

  # Otherwise, prepare storage for the edit costs
  # Only store the current and previous cost rows, adding a single
  # element to the beginning for the cost of inserting i characters

  cdef Py_ssize_t *current   = <Py_ssize_t *>malloc( (m+1)*sizeof(Py_ssize_t))
  cdef Py_ssize_t *previous1 = <Py_ssize_t *>malloc( (m+1)*sizeof(Py_ssize_t))
  cdef Py_ssize_t *previous2 = <Py_ssize_t *>malloc( (m+1)*sizeof(Py_ssize_t))

  # Start by assigning the cost of transforming an empty s1 into s2[0:m] by
  # inserting 0..m elements
  # Initialize previous two cost rows to zero, since the values are not used
  # and are going to be overwritten

  for i in range(m+1):
    current[i]   = i
    previous1[i] = 0
    previous2[i] = 0

  cdef char *ss1 = s1
  cdef char *ss2 = s2
  cdef char c1,c2

  # For each location in s1
  for i in range(n):
    c1 = ss1[i]

    # Swap current and previous cost row storage to recycle the old
    # 'previous2' as the new 'current'
    previous2,previous1,current = previous1,current,previous2

    # Initialize the cost of inserting characters up to and including i
    current[0] = i+1

    # Update minimum match, insertion, and deletion costs for each
    # location in s2
    for j in range(m):
      c2 = ss2[j]

      if c1==c2:
        cost = 0
      else:
        cost = 1

      # Compute cost of transforming s1[0:i+1]->s2[0:j+1] allowing the
      # following edit operations:

      # Match:        transform s1[0:i]->s2[0:j] + 0, if s1[i]==s2[j]
      # Substitution: transform s1[0:i]->s2[0:j] + 1, if s1[i]!=s2[j]
      match  = previous1[j]   + cost

      # Insert: transform s1[0:i+1]->s2[0:j] and insert s2[j]
      insert = current[j]     + 1

      # Delete: transform s1[0:i]->s2[0:j+1] and delete s1[i]
      delete = previous1[j+1] + 1

      # Transpose: transform s1[0:i-1]->s2[0:j-1] + 1,
      #            if s1[i]==s2[j-1] and s1[i-1]==s2[j]
      trans  = match
      if i and j and c1==ss2[j-1] and ss1[i-1]==c2:
        trans = previous2[j-1]+1

      # Take minimum cost operation
      current[j+1] = min4(match, insert, delete, trans)

  # Return the minimum edit cost for both complete sequences.  i.e. the cost
  # transforming s1[0:i+1]->s2[0:j+1], which is current[-1].

  distance = current[m]

  free(current)
  free(previous1)
  free(previous2)

  return distance


cdef inline _op_str(char op):
  if op=='S':
    opstr = 'S'
  elif op=='N':
    opstr = 'N'
  elif op=='M':
    opstr = 'M'
  elif op=='=':
    opstr = '='
  elif op=='X':
    opstr = 'X'
  elif op=='I':
    opstr = 'I'
  elif op=='D':
    opstr = 'D'
  elif op=='T':
    opstr = 'T'
  else:
    raise ValueError('Unknown op=%s' % op)
  return opstr


cdef _roll_cigar(Py_ssize_t n, Py_ssize_t m, Py_ssize_t i, Py_ssize_t j, char *edits):
  '''
  Compute the sequence of edits required to transform sequence s1 to s2
  using the operations encoded in the supplied matrix of edit operations.
  Used internally for edit matrices generated by levenshtein_sequence and
  damerau_levenshtein_sequence
  '''
  cdef Py_ssize_t k,count
  cdef char op

  k = 0
  cdef char *igar = <char *>malloc(max2(n,m)*sizeof(char))

  while n-1>i:
    igar[k] = 'S'
    k += 1
    n -= 1

  while m-1>j:
    igar[k] = 'N'
    k += 1
    m -= 1

  while i>=0 and j>=0:
    igar[k] = op = edits[m*i+j]
    k += 1

    if op=='M' or op=='=' or op=='X':
      i -= 1
      j -= 1
    elif op=='D':
      i -= 1
    elif op=='I':
      j -= 1
    elif op=='T':
      i -= 2
      j -= 2
    else:
      free(igar)
      raise ValueError('Invalid edit operation')

  while j>=0:
    igar[k] = 'N'
    k += 1
    j -= 1

  while i>=0:
    igar[k] = 'S'
    k += 1
    i -= 1

  cdef list cigar = []

  op = 0
  count = 0

  for k in range(k-1,-1,-1):
    if igar[k]==op:
      count += 1
    else:
      if count:
        cigar.append( CigarOp(_op_str(op),count) )
      op = igar[k]
      count = 1

  if count:
    cigar.append( CigarOp(_op_str(op),count) )

  free(igar)
  return cigar


def smith_waterman(s1, s2, Py_ssize_t match_score=1, Py_ssize_t mismatch_score=-1, Py_ssize_t gap_score=-1):
  '''
  Align s1 to s2 using the Smith-Waterman algorithm for local ungapped
  alignment.  An alignment score and sequence of alignment operations are returned.

  The operations to align s1 to s2 are returned as a sequence, represented
  by extended CIGAR (Compact Idiosyncratic Gapped Alignment Report)
  operations of the form:

    Match:         CigarOp(op='=', count=n)
    Mismatch:      CigarOp(op='X', count=n)
    Insertion:     CigarOp(op='I', count=n)
    Deletion:      CigarOp(op='D', count=n)

  Match operations are inclusive of matching and mismatch characters

  See: http://en.wikipedia.org/wiki/Smith%E2%80%93Waterman_algorithm

       Smith, Temple F.; and Waterman, Michael S. (1981). "Identification
       of Common Molecular Subsequences". Journal of Molecular Biology 147: 195–197.
       http://gel.ym.edu.tw/~chc/AB_papers/03.pdf


  This implementation is based on a standard dynamic programming algorithm,
  requiring O(N*M) time and space, where N and M are the lengths of the two
  sequences.  See the following for more information on these concepts:

    http://en.wikipedia.org/wiki/Dynamic_programming
    http://en.wikipedia.org/wiki/Big_O_notation

  The the cost to transform s1[:i]->s2[:j] is based on the following
  recurrence:

              |  i                       if i>=0, j=0  (delete s1[:i])
              |  j                       if i =0, j>0  (insert s2[:j])
  cost[i,j] = |
              |     | 0
              |     | cost[i-1,j-1] + m   if c1==c2     (match: perfect)
              | min | cost[i-1,j-1] + mm  if c1!=c2     (match: substitution)
              |     | cost[i,  j-1] + g                (insert c2)
              |     | cost[i-1,j  ] + g                (delete c1)

  where c1=s1[i-1], c2=s2[j-1].  The resulting minimum edit distance is then
  cost[i,j] and the edit sequence is obtained by keeping note of which
  operation was selected at each step and backtracking from the end to the
  beginning.  This implementation saves space by only storing the last two
  cost rows at any given time (cost[i-1], and cost[i]).

  >>> s1,s2='b','abc'
  >>> score,cigar = smith_waterman(s1,s2)
  >>> score
  1
  >>> cigar_to_string(cigar)
  '1N1=1N'
  >>> a1,a2 = cigar_alignment(s1,s2,cigar)
  >>> print "'%s'\\n'%s'" % (a1,a2) # doctest: +NORMALIZE_WHITESPACE
  ' b '
  'a.c'

  >>> s1,s2='abc','b'
  >>> score,cigar = smith_waterman(s1,s2)
  >>> score
  1
  >>> cigar_to_string(cigar)
  '1S1=1S'
  >>> a1,a2 = cigar_alignment(s1,s2,cigar)
  >>> print "'%s'\\n'%s'" % (a1,a2) # doctest: +NORMALIZE_WHITESPACE
  'abc'
  ' . '

  >>> s1,s2='abcbd','acd'
  >>> score,cigar = smith_waterman(s1,s2,match_score=2)
  >>> score
  4
  >>> cigar_to_string(cigar)
  '1=1D1=1D1='
  >>> a1,a2 = cigar_alignment(s1,s2,cigar)
  >>> print "'%s'\\n'%s'" % (a1,a2) # doctest: +NORMALIZE_WHITESPACE
  'abcbd'
  '.-.-.'

  >>> s2,s1='abcbd','acd'
  >>> score,cigar = smith_waterman(s1,s2,match_score=2)
  >>> score
  4
  >>> cigar_to_string(cigar)
  '1=1I1=1I1='
  >>> a1,a2 = cigar_alignment(s1,s2,cigar)
  >>> print "'%s'\\n'%s'" % (a1,a2) # doctest: +NORMALIZE_WHITESPACE
  'a-c-d'
  '.b.b.'

  >>> s1,s2='abcbd','beb'
  >>> score,cigar = smith_waterman(s1,s2,match_score=2)
  >>> score
  3
  >>> cigar_to_string(cigar)
  '1S1=1X1=1S'
  >>> a1,a2 = cigar_alignment(s1,s2,cigar)
  >>> print "'%s'\\n'%s'" % (a1,a2) # doctest: +NORMALIZE_WHITESPACE
  'abcbd'
  ' .e. '
  '''
  # Prepare storage for the edit costs and operations
  # Allocate an empty character matrix to track the best edits at each step
  # in order to reconstruct an optimal sequence at the end

  cdef Py_ssize_t n = PyString_Size(s1)
  cdef Py_ssize_t m = PyString_Size(s2)
  cdef Py_ssize_t i,j,max_i,max_j,max_cost,mcost,match,insert,delete
  cdef char *edits = <char*>malloc(n*m*sizeof(char))
  cdef int  *cost  = <int*>malloc((n+1)*(m+1)*sizeof(int))
  cdef char *ss1   = s1
  cdef char *ss2   = s2
  cdef char c1,c2,op

  max_i = max_j = max_cost = 0

  for j in range(m+1):
    cost[j] = 0

  for i in range(n):
    c1 = ss1[i]

    cost[(m+1)*(i+1)] = 0

    for j in range(m):
      c2 = ss2[j]

      # Compute cost of transforming s1[0:i+1]->s2[0:j+1] allowing the
      # following edit operations:

      # Match/Mismatch: transform s1[0:i]->s2[0:j] + match/mismatch cost
      match  = cost[(m+1)*i+j]

      if c1==c2:
        match += match_score
      else:
        match += mismatch_score

      # Insert: transform s1[0:i+1]->s2[0:j] and insert s2[j]
      insert = cost[(m+1)*(i+1)+j] + gap_score

      # Delete: transform s1[0:i]->s2[0:j+1] and delete s1[i]
      delete = cost[(m+1)*i+j+1] + gap_score

      # Take best costing operation
      cost[(m+1)*(i+1)+j+1] = mcost = max4(0, match, insert, delete)

      if mcost>max_cost:
         max_cost = mcost
         max_i    = i
         max_j    = j

      # Record the operation chosen, with preference for (mis)matches over
      # insertions over deletions.  This ambiguity for equal cost options
      # implies that there may not be a unique optimum edit sequence, but
      # one or more sequences of equal length.
      if mcost==match and c1==c2:
        op = '='
      elif mcost==match:
        op = 'X'
      elif mcost==insert:
        op = 'I'
      else:
        op = 'D'

      edits[m*i+j]=op

  # Build and return a minimal edit sequence using the saved operations
  score = cost[(m+1)*(max_i+1)+max_j+1]
  cigar = _roll_cigar(n,m,max_i,max_j,edits)

  free(edits)
  free(cost)

  return score,cigar


def smith_waterman_gotoh(s1, s2, Py_ssize_t match_score=1, Py_ssize_t mismatch_score=-1,
                                 Py_ssize_t gap_open_score=-2, Py_ssize_t gap_extend_score=-1):
  '''
  Align s1 to s2 using the Smith-Waterman algorithm for local ungapped
  alignment.  An alignment score and sequence of alignment operations are returned.

  The operations to align s1 to s2 are returned as a sequence, represented
  by extended CIGAR (Compact Idiosyncratic Gapped Alignment Report)
  operations of the form:

    Match:         CigarOp(op='=', count=n)
    Mismatch:      CigarOp(op='X', count=n)
    Insertion:     CigarOp(op='I', count=n)
    Deletion:      CigarOp(op='D', count=n)

  Match operations are inclusive of matching and mismatch characters

  See: http://en.wikipedia.org/wiki/Smith%E2%80%93Waterman_algorithm

       Smith, Temple F.; and Waterman, Michael S. (1981). "Identification
       of Common Molecular Subsequences". Journal of Molecular Biology 147: 195–197.
       http://gel.ym.edu.tw/~chc/AB_papers/03.pdf


  This implementation is based on a standard dynamic programming algorithm,
  requiring O(N*M) time and space, where N and M are the lengths of the two
  sequences.  See the following for more information on these concepts:

    http://en.wikipedia.org/wiki/Dynamic_programming
    http://en.wikipedia.org/wiki/Big_O_notation

  The the cost to transform s1[:i]->s2[:j] is based on the following
  recurrence:

              |  i                       if i>=0, j=0  (delete s1[:i])
              |  j                       if i =0, j>0  (insert s2[:j])
  cost[i,j] = |
              |     | 0
              |     | cost[i-1,j-1] + m   if c1==c2     (match: perfect)
              | min | cost[i-1,j-1] + mm  if c1!=c2     (match: substitution)
              |     | cost[i,  j-1] + g                (insert c2)
              |     | cost[i-1,j  ] + g                (delete c1)

  where c1=s1[i-1], c2=s2[j-1].  The resulting minimum edit distance is then
  cost[i,j] and the edit sequence is obtained by keeping note of which
  operation was selected at each step and backtracking from the end to the
  beginning.  This implementation saves space by only storing the last two
  cost rows at any given time (cost[i-1], and cost[i]).

  >>> s1,s2='b','abc'
  >>> score,cigar = smith_waterman_gotoh(s1,s2)
  >>> score
  1
  >>> cigar_to_string(cigar)
  '1N1=1N'
  >>> a1,a2 = cigar_alignment(s1,s2,cigar)
  >>> print "'%s'\\n'%s'" % (a1,a2) # doctest: +NORMALIZE_WHITESPACE
  ' b '
  'a.c'

  >>> s1,s2='abc','b'
  >>> score,cigar = smith_waterman_gotoh(s1,s2)
  >>> score
  1
  >>> cigar_to_string(cigar)
  '1S1=1S'
  >>> a1,a2 = cigar_alignment(s1,s2,cigar)
  >>> print "'%s'\\n'%s'" % (a1,a2) # doctest: +NORMALIZE_WHITESPACE
  'abc'
  ' . '

  >>> s1,s2='abbcbbd','acd'
  >>> score,cigar = smith_waterman_gotoh(s1,s2,match_score=4)
  >>> score
  6
  >>> cigar_to_string(cigar)
  '1=2D1=2D1='
  >>> a1,a2 = cigar_alignment(s1,s2,cigar)
  >>> print "'%s'\\n'%s'" % (a1,a2) # doctest: +NORMALIZE_WHITESPACE
  'abbcbbd'
  '.--.--.'

  >>> s1,s2='abbcbbd','acd'
  >>> score,cigar = smith_waterman_gotoh(s1,s2,match_score=3,gap_extend_score=0)
  >>> score
  5
  >>> cigar_to_string(cigar)
  '1=2D1=2D1='
  >>> a1,a2 = cigar_alignment(s1,s2,cigar)
  >>> print "'%s'\\n'%s'" % (a1,a2) # doctest: +NORMALIZE_WHITESPACE
  'abbcbbd'
  '.--.--.'
  '''
  # Fall back to the standard Smith Waterman when the overhead of the Gotoh
  # scoring is not needed
  if gap_open_score==gap_extend_score:
    return smith_waterman(s1, s2, match_score=match_score, mismatch_score=mismatch_score,
                                  gap_score=gap_open_score)

  cdef Py_ssize_t n = PyString_Size(s1)
  cdef Py_ssize_t m = PyString_Size(s2)
  cdef Py_ssize_t i,j,max_i,max_j,max_cost,mcost,match,insert,delete
  cdef char *edits = <char*>calloc(n*m, sizeof(char))
  cdef int  *cost  = <int*>calloc((n+1)*(m+1), sizeof(int))
  cdef int  *gap1  = <int*>calloc((n+1)*(m+1), sizeof(int))
  cdef int  *gap2  = <int*>calloc((n+1)*(m+1), sizeof(int))
  cdef char *ss1   = s1
  cdef char *ss2   = s2
  cdef char c1,c2,op

  max_i = max_j = max_cost = 0

  for j in range(m+1):
    cost[j] = gap1[j] = gap2[j] = 0

  for i in range(n):
    c1 = ss1[i]

    cost[(m+1)*(i+1)] = 0
    gap1[(m+1)*(i+1)] = 0
    gap2[(m+1)*(i+1)] = 0

    for j in range(m):
      c2 = ss2[j]

      # Compute cost of transforming s1[0:i+1]->s2[0:j+1] allowing the
      # following edit operations:

      # Match/Mismatch: transform s1[0:i]->s2[0:j] + match/mismatch cost
      match  = cost[(m+1)*i+j]

      if c1==c2:
        match += match_score
      else:
        match += mismatch_score

      # Insert: transform s1[0:i+1]->s2[0:j] and insert s2[j]
      insert = gap1[(m+1)*(i+1)+j+1] = max2(gap1[(m+1)*(i+1)+j] + gap_extend_score,
                                            cost[(m+1)*(i+1)+j] + gap_open_score)

      # Delete: transform s1[0:i]->s2[0:j+1] and delete s1[i]
      delete = gap2[(m+1)*(i+1)+j+1] = max2(gap2[(m+1)*i+j+1] + gap_extend_score,
                                            cost[(m+1)*i+j+1] + gap_open_score)

      # Take best costing operation
      cost[(m+1)*(i+1)+j+1] = mcost = max4(0, match, insert, delete)

      # Record the operation chosen, with preference for (mis)matches over
      # insertions over deletions.  This ambiguity for equal cost options
      # implies that there may not be a unique optimum edit sequence, but
      # one or more sequences of equal length.
      if mcost>max_cost:
         max_cost = mcost
         max_i    = i
         max_j    = j

      # Record the operation chosen, with preference for (mis)matches over
      # insertions over deletions.  This ambiguity for equal cost options
      # implies that there may not be a unique optimum edit sequence, but
      # one or more sequences of equal length.
      if mcost==match and c1==c2:
        op = '='
      elif mcost==match:
        op = 'X'
      elif mcost==insert:
        op = 'I'
      else:
        op = 'D'

      edits[m*i+j]=op

  # Build and return a minimal edit sequence using the saved operations
  score = cost[(m+1)*(max_i+1)+max_j+1]
  cigar = _roll_cigar(n,m,max_i,max_j,edits)

  free(edits)
  free(cost)
  free(gap2)
  free(gap1)

  return score,cigar
