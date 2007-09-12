# -*- coding: utf-8 -*-
'''
File:          genoarray.py

Authors:       Kevin Jacobs (jacobske@bioinformed.com)

Created:       2007-04-10

Abstract:      Efficient bit-packed genotype array representation

Requires:      Python 2.5

Revision:      $Id$
'''

from   __future__ import division

__copyright__ = 'Copyright (c) 2007 Science Applications International Corporation ("SAIC")'
__license__   = 'See GLU license for terms by running: glu license'


__all__ = ['Genotype','UnphasedMarkerModel','GenotypeArray','GenotypeError','GenotypeArrayDescriptor']


class GenotypeError(ValueError): pass


try:
  #raise ImportError    # Uncomment to test pure-Python implementation
  from   _genoarray import (GenotypeArray, Genotype, GenotypeArrayDescriptor, UnphasedMarkerModel,
                            genoarray_concordance)

except ImportError:
  from   array     import array
  from   math      import log, ceil
  from   itertools import izip

  from   bitarray  import getbits,setbits

  MISSING,HEMIZYGOTE,HETEROZYGOTE,HOMOZYGOTE=range(4)

  class Genotype(object):
    '''
    bit-packed genotype representation
    '''
    __slots__ = ('model','allele1','allele2','index','gclass')

    def __init__(self, model, allele1, allele2, index):
      '''
      Construct a new Genotype and determine the genotype class: 
      MISSING or HEMIZYGOTE or HOMOZYGOTE or HETEROZYGOTE

      @param    model: genotype representation
      @type     model: UnphasedMarkerRepresentation or similar object
      @param  allele1: the first allele
      @type   allele1: str
      @param  allele2: the second allele
      @type   allele2: str
      @param    index: FIX ME 
      @type     index: FIX ME
      '''
      self.model   = model
      self.allele1 = allele1
      self.allele2 = allele2
      self.index   = index

      missing1 = allele1 is None
      missing2 = allele2 is None

      if missing1 and missing2:
        self.gclass = MISSING
      elif missing1 or missing2:
        self.gclass = HEMIZYGOTE
      elif allele1 is allele2:
        self.gclass = HOMOZYGOTE
      else:
        if allele1 == allele2:
          raise GenotypeError('Attempt to add non-singleton alleles')
        self.gclass = HETEROZYGOTE

    def alleles(self):
      '''
      Return a tuple of alleles
      '''
      return (self.allele1,self.allele2)

    def heterozygote(self):
      '''
      Test if the Genotype is heterozygote
      '''
      return self.gclass == HETEROZYGOTE

    def homozygote(self):
      '''
      Test if the Genotype is homozygote
      '''
      return self.gclass == HOMOZYGOTE

    def hemizygote(self):
      '''
      Test if the Genotype is hemizygote
      '''
      return self.gclass == HEMIZYGOTE

    def missing(self):
      '''
      Test if the alleles of the Genotype are all missing
      '''
      return self.gclass == MISSING

    def __nonzero__(self):
      '''
      Test if the alleles of the Genotype are not all missing
      '''
      return self.gclass != MISSING

    def __getitem__(self,i):
      '''
      Retrieve the allele as specified
      '''
      return self.alleles()[i]

    def __len__(self):
      '''
      Return the number of alleles of the Genotype
      '''
      return len([a for a in self.alleles() if a is not None])

    def __repr__(self):
      '''
      Return a string representation of the alleles
      '''
      #return '<Genotype: %s/%s at 0x%X>' % (self.allele1,self.allele2,id(self))
      return repr(self.alleles())

    def __eq__(self,other):
      '''
      Test if the Genotype object that was passed in is the same as the current one

      @param other: the Genotype object to be compared to the current one
      @type  other: Genotype object
      '''
      geno_self  = isinstance(self,Genotype)
      geno_other = isinstance(other,Genotype)

      if geno_self and geno_other:
        return self is other

      if geno_self:
        self = self.alleles()
      if geno_other:
        other = other.alleles()

      if not isinstance(self, tuple) or len(self) !=2 or \
         not isinstance(other,tuple) or len(other)!=2:
        return NotImplemented

      return self==other

    def __ne__(self,other):
      '''
      Test if the Genotype object that was passed in is not the same as the current one

      @param other: the Genotype object to be compared to the current one
      @type  other: Genotype object
      '''
      geno_self  = isinstance(self,Genotype)
      geno_other = isinstance(other,Genotype)

      if geno_self and geno_other:
        return self is not other

      if geno_self:
        self = self.alleles()
      if geno_other:
        other = other.alleles()

      if not isinstance(self, tuple) or len(self) !=2 or \
         not isinstance(other,tuple) or len(other)!=2:
        return NotImplemented

      return self!=other

    def __lt__(self,other):
      '''
      Test if the Genotype object that was passed in has a tuple of two alleles
      and the tuple is greater in an alphanumerical order compared to the current one

      @param other: the Genotype object to be compared to the current one
      @type  other: Genotype object
      '''
      if isinstance(self,Genotype):
        self = self.alleles()
      if isinstance(other,Genotype):
        other = other.alleles()

      if not isinstance(self, tuple) or len(self) !=2 or \
         not isinstance(other,tuple) or len(other)!=2:
        return NotImplemented

      return self<other

    def __le__(self,other):
      '''
      Test if the Genotype object that was passed in is the same as the current one
      Or
      Test if the Genotype object that was passed in has a tuple of two alleles
      and the tuple is greater in an alphanumerical order compared to the current one

      @param other: the Genotype object to be compared to the current one
      @type  other: Genotype object
      '''

      if isinstance(self,Genotype):
        self = self.alleles()
      if isinstance(other,Genotype):
        other = other.alleles()

      if not isinstance(self, tuple) or len(self) !=2 or \
         not isinstance(other,tuple) or len(other)!=2:
        return NotImplemented

      return self<=other

  def genotype_bit_size(n,allow_hemizygote):
    '''
    Return the genotype bit size 

    @param                 n: FIX ME
    @type                  n: FIX ME
    @param  allow_hemizygote: flag indicating if hemizygote is allowed in the representation
    @type   allow_hemizygote: bool
    @return                 : the bit size  
    @rtype                  : int
    '''

    if allow_hemizygote:
      m = (n+1)*(n+2)//2
    else:
      m = n*(n+1)//2 + 1

    return int(ceil(log(m)/log(2.0)))

  def byte_array_size(nbits):
    '''
    Return the byte array size

    @param  nbits: bit size 
    @type   nbits: int
    '''
    return int(ceil(nbits/8))


  class GenotypeArrayDescriptor(object):
    __slots__ = ('models','offsets','byte_size','bit_size')

    def __init__(self, models, initial_offset=0):
      '''
      Construct a new GenotypeArrayDescriptor
      '''
      n = len(models)
      offsets = [0]*(n+1)

      offsets[0] = initial_offset
      for i,m in enumerate(models):
        offsets[i+1] = offsets[i] + m.bit_size

      self.models    = models
      self.offsets   = offsets
      self.bit_size  = offsets[-1]
      self.byte_size = byte_array_size(self.bit_size)

    def __len__(self):
      return len(self.models)


  class GenotypeArray(object):
    __slots__ = ('descriptor','data')

    def __init__(self, descriptor, genos=None):
      '''
      Construct a new GenotypeArray out of the GenotypeArrayDescriptor or GenotypeArray object that was passed in

      @param   descriptor: bit-packed genotype array representation
      @type    descriptor: GenotypeArrayDescriptor or GenotypeArray object
      @param        genos: genotype stream
      @type         genos: sequence of genotype strings
      '''
      if isinstance(descriptor, GenotypeArrayDescriptor):
        self.descriptor = descriptor
      elif isinstance(descriptor, GenotypeArray):
        self.descriptor = descriptor.descriptor

      self.data = array('B', [0]*self.descriptor.byte_size)

      if genos is not None:
        self[:] = genos

    def __len__(self):
      '''
      Return the number of models in the current GenotypeArray
      '''
      return len(self.descriptor.models)

    def __getitem__(self, i):
      '''
      Return the specified genotype in the current GenotypeArray

      @param       i: bit index into data from which to begin reading
      @type        i: int
      '''
      descr = self.descriptor

      if isinstance(i,slice):
        x = xrange(*i.indices(len(descr.models)))
        return [ self[i] for i in x ]

      model    = descr.models[i]
      startbit = descr.offsets[i]
      width    = model.bit_size
      j        = getbits(self.data, startbit, width)

      return model.genotypes[j]

    def __setitem__(self, i, geno):
      '''
      Reset the specified genotype in the current GenotypeArray

      @param       i: bit index into data from which to begin replacing
      @type        i: int
      @param    geno: genotype representation
      @type     geno: slice, tuple, Genotype object
      '''
      descr = self.descriptor

      if isinstance(i,slice):
        x = xrange(*i.indices(len(descr.models)))
        try:
          n = len(geno)
        except TypeError:
          geno = list(geno)
          n = len(geno)
        if len(x) != n:
          raise IndexError('Invalid slice')
        for i,j in enumerate(x):
          self[j] = geno[i]
        return
      elif isinstance(geno,tuple) and len(geno) == 2:
        geno = descr.models[i][geno]
      elif not isinstance(geno,Genotype):
        raise GenotypeError('Invalid genotype: %s' % geno)

      model    = descr.models[i]
      startbit = descr.offsets[i]
      width    = model.bit_size

      assert geno.model is model
      setbits(self.data, startbit, geno.index, width)

    def __repr__(self):
      return repr(list(self))


  class UnphasedMarkerModel(object):
    '''
    bit-packed unphased marker representation where the genotype representation
    and internal representation are the same.
    '''

    __slots__ = ('alleles','genotypes','genomap','bit_size','allow_hemizygote','max_allles')

    def __init__(self, allow_hemizygote=False, max_alleles=None):
      '''
      Construct a new UnphasedMarkerModel

      This class represents bidirectional mappings of genotypes between
      strings and Python objects.  The object representation of a genotype is
      a list of two alleles or up to the max_alleles. Given this representation,
      alleles need not be known in advance.  

      @param  allow_hemizygote: flag indicating if hemizygote is allowed in the representation
      @type   allow_hemizygote: bool
      @param       max_alleles: the maximun number of alleles allowed in the representation. Default is None
      @type        max_alleles: int or None
      '''

      self.genomap          = {}
      self.genotypes        = []
      self.alleles          = []
      self.max_alleles      = max(2,max_alleles)
      self.bit_size         = genotype_bit_size(self.max_alleles,allow_hemizygote)
      self.allow_hemizygote = allow_hemizygote
      self.add_genotype( (None,None) )

    def get_allele(self, allele):
      '''
      Return the allele that was passed in from the current UnphasedMarkerModel
      '''
      return self.alleles.index(allele)

    def add_allele(self, allele):
      '''
      Add the allele that was passed in into the current UnphasedMarkerModel
      '''
      if allele in self.alleles:
        return self.alleles.index(allele)

      n = len(self.alleles)
      new_width = genotype_bit_size(n,self.allow_hemizygote)
      if new_width > self.bit_size:
        raise GenotypeError('Allele cannot be added to model due to fixed bit width')
      self.alleles.append(allele)

      return n

    def get_genotype(self, geno):
      '''
      Return the genotype that was passed in from the current UnphasedMarkerModel
      '''
      return self.genomap[geno]

    __getitem__ = get_genotype

    def add_genotype(self, geno):
      '''
      Add the genotype that was passed in into the current UnphasedMarkerModel
      '''
      g = self.genomap.get(geno)

      # If the genotype has not already been seen for this locus
      if g is not None:
        return g

      allele1,allele2 = sorted(geno)

      index1 = self.add_allele(allele1)
      index2 = self.add_allele(allele2)

      allele1 = self.alleles[index1]
      allele2 = self.alleles[index2]

      # Create and save new genotype
      g = Genotype(self, allele1, allele2, len(self.genotypes))

      if not self.allow_hemizygote and g.hemizygote():
        raise GenotypeError('Genotype model does not all hemizygous genotypes')

      self.genotypes.append(g)
      self.genomap[allele1,allele2] = g
      self.genomap[allele2,allele1] = g

      return g


  def genoarray_concordance(genos1, genos2):
    '''
    Generate simple concordance statistics from two genotype arrays

    @param genos1: the first genotypearray that was passed in
    @type  genos1: GenotypeArray object
    @param genos2: the second genotypearray that was passed in
    @type  genos2: GenotypeArray object
    @return      : a tuple of concordance stats
    @rtype       : tuple of ints
    '''
    if len(genos1) != len(genos2):
      raise ValueError("genotype vector sizes do not match: %zd != %zd" % (len(genos1),len(genos2)))

    concordant = comparisons = 0
    for a,b in izip(genos1,genos2):
      if a and b:
        if a is b:
          concordant += 1
        comparisons += 1

    return concordant,comparisons


def model_from_alleles(alleles, allow_hemizygote=False, max_alleles=None):
  '''
  Build an UnphasedMarkerModel from the alleles that were passed in

  @param           alleles: sequence of alleles
  @param           alleles: sequence of strings
  @param  allow_hemizygote: flag indicating if hemizygote is allowed in the representation. Default is False
  @type   allow_hemizygote: bool
  @param       max_alleles: the maximun number of alleles allowed in the representation. Default is None
  @type        max_alleles: int or None
  @return:                  the UnphasedMarkerModel built from the supplied alleles 
  @rtype:                   an UnphasedMarkerModel object

  '''

  alleles = sorted(set(a for a in alleles if a is not None))
  n = len(alleles)

  if not max_alleles:
    max_alleles = n

  if allow_hemizygote:
    alleles = [None]+alleles

  n = len(alleles)
  genos = [ (alleles[i],alleles[j]) for i in range(n) for j in range(i,n) ]

  model = UnphasedMarkerModel(allow_hemizygote=allow_hemizygote,max_alleles=max_alleles)
  for g in genos:
    model.add_genotype(g)

  return model


def model_from_genotypes(genotypes, allow_hemizygote=None, max_alleles=None):
  '''
  Build an UnphasedMarkerModel from the genotypes that were passed in

  @param         genotypes: sequence of genotypes
  @param         genotypes: sequence of strings
  @param  allow_hemizygote: flag indicating if hemizygote is allowed in the representation. Default is False
  @type   allow_hemizygote: bool
  @param       max_alleles: the maximun number of alleles allowed in the representation. Default is None
  @type        max_alleles: int or None
  @return:                  the UnphasedMarkerModel built from the supplied genotypes
  @rtype:                   an UnphasedMarkerModel object
  '''

  alleles = sorted(set(a for g in genoset for a in g if a is not None))
  return model_from_alleles_and_genotypes(alleles, genotypes, allow_hemizygote, max_alleles)


def model_from_alleles_and_genotypes(alleles, genotypes, allow_hemizygote=False, max_alleles=None):
  '''
  Build an UnphasedMarkerModel from the alleles and genotypes that were passed in

  @param           alleles: sequence of alleles
  @param           alleles: sequence
  @param         genotypes: sequence of genotypes
  @param         genotypes: sequence
  @param  allow_hemizygote: flag indicating if hemizygote is allowed in the representation. Default is False
  @type   allow_hemizygote: bool
  @param       max_alleles: the maximun number of alleles allowed in the representation. Default is None
  @type        max_alleles: int or None
  @return:                  the UnphasedMarkerModel built from the supplied alleles and genotypes
  @rtype:                   an UnphasedMarkerModel object
  '''

  genoset = set(genotypes)

  if not allow_hemizygote:
    def hemi(g):
      return (g[0] is None) ^ (g[1] is None)

    hemi = any(hemi(g) for g in genoset)

    if allow_hemizygote is not None and hemi:
      raise GenotypeError('Genotype model does not allow hemizygous genotypes')

    allow_hemizygote = hemi

  n = len(set(alleles))

  if not max_alleles:
    max_alleles = n
  elif n > max_alleles:
    raise GenotypeError('Genotype model supports at most %d alleles, %d specified' % (max_alleles,n))

  model = UnphasedMarkerModel(allow_hemizygote=allow_hemizygote,max_alleles=max_alleles)

  for a in alleles:
    model.add_allele(a)

  for g in genotypes:
    model.add_genotype(g)

  if allow_hemizygote:
    alleles = [None]+alleles

  all_genos = ( (alleles[i],alleles[j]) for i in range(n) for j in range(i,n) )

  for g in all_genos:
    model.add_genotype(g)

  return model


def model_from_complete_alleles_and_genotypes(alleles, genotypes, allow_hemizygote=False, max_alleles=None):
  '''
  Build an UnphasedMarkerModel from the alleles and genotypes that were passed in

  @param           alleles: sequence of alleles
  @param           alleles: sequence
  @param         genotypes: sequence of genotypes
  @param         genotypes: sequence
  @param  allow_hemizygote: flag indicating if hemizygote is allowed in the representation. Default is False
  @type   allow_hemizygote: bool
  @param       max_alleles: the maximun number of alleles allowed in the representation. Default is None
  @type        max_alleles: int or None
  @return:                  the UnphasedMarkerModel built from the supplied alleles and genotypes
  @rtype:                   an UnphasedMarkerModel object
  '''

  if not max_alleles:
    max_alleles = len(set(alleles))

  model = UnphasedMarkerModel(allow_hemizygote=allow_hemizygote,max_alleles=max_alleles)

  for a in alleles:
    model.add_allele(a)

  for g in genotypes:
    model.add_genotype(g)

  return model


def test_concordance_generic():
  '''
  >>> model = model_from_alleles('AB')
  >>> descr = GenotypeArrayDescriptor([model]*6)
  >>> model.genotypes
  [(None, None), ('A', 'A'), ('A', 'B'), ('B', 'B')]
  >>> NN,AA,AB,BB = model.genotypes

  >>> def g(genos):
  ...   return GenotypeArray(descr,genos)[:]

  >>> genoarray_concordance(g([NN,AA,AB,AB,BB,NN]),g([NN,AA,AB,AB,BB,NN]))
  (4, 4)
  >>> genoarray_concordance(g([NN,NN,NN,NN,NN,NN]),g([NN,AA,AB,AB,BB,NN]))
  (0, 0)
  >>> genoarray_concordance(g([NN,AA,AB,AB,BB,NN]),g([NN,NN,NN,NN,NN,NN]))
  (0, 0)
  >>> genoarray_concordance(g([AA,AB,AB,BB,NN,BB]),g([NN,AA,AB,AB,BB,NN]))
  (1, 3)
  '''

def test_concordance_4bit():
  '''
  >>> model = model_from_alleles('AB',max_alleles=5)
  >>> model.bit_size
  4L

  Test even number of genotypes

  >>> model.genotypes
  [(None, None), ('A', 'A'), ('A', 'B'), ('B', 'B')]
  >>> NN,AA,AB,BB = model.genotypes

  >>> def g(genos):
  ...   return GenotypeArray(descr,genos)

  >>> descr = GenotypeArrayDescriptor([model]*6)
  >>> genoarray_concordance(g([NN,AA,AB,AB,BB,NN]),g([NN,AA,AB,AB,BB,NN]))
  (4, 4)
  >>> genoarray_concordance(g([NN,NN,NN,NN,NN,NN]),g([NN,AA,AB,AB,BB,NN]))
  (0, 0)
  >>> genoarray_concordance(g([NN,AA,AB,AB,BB,NN]),g([NN,NN,NN,NN,NN,NN]))
  (0, 0)
  >>> genoarray_concordance(g([AA,AB,AB,BB,NN,BB]),g([NN,AA,AB,AB,BB,NN]))
  (1, 3)

  Test odd number of genotypes

  >>> descr = GenotypeArrayDescriptor([model]*7)
  >>> genoarray_concordance(g([NN,AA,AB,AB,BB,NN,AB]),g([NN,AA,AB,AB,BB,NN,AB]))
  (5, 5)
  >>> genoarray_concordance(g([NN,NN,NN,NN,NN,NN,NN]),g([NN,AA,AB,AB,BB,NN,AB]))
  (0, 0)
  >>> genoarray_concordance(g([NN,AA,AB,AB,BB,NN,AA]),g([NN,NN,NN,NN,NN,NN,NN]))
  (0, 0)
  >>> genoarray_concordance(g([AA,AB,AB,BB,NN,BB,AB]),g([NN,AA,AB,AB,BB,NN,BB]))
  (1, 4)
  '''

def test_concordance_2bit():
  '''
  >>> model = model_from_alleles('AB')
  >>> model.bit_size
  2L

  Test even number of genotypes

  >>> descr = GenotypeArrayDescriptor([model]*6)
  >>> model.genotypes
  [(None, None), ('A', 'A'), ('A', 'B'), ('B', 'B')]
  >>> NN,AA,AB,BB = model.genotypes

  >>> def g(genos):
  ...   return GenotypeArray(descr,genos)

  >>> genoarray_concordance(g([NN,AA,AB,AB,BB,NN]),g([NN,AA,AB,AB,BB,NN]))
  (4, 4)
  >>> genoarray_concordance(g([NN,NN,NN,NN,NN,NN]),g([NN,AA,AB,AB,BB,NN]))
  (0, 0)
  >>> genoarray_concordance(g([NN,AA,AB,AB,BB,NN]),g([NN,NN,NN,NN,NN,NN]))
  (0, 0)
  >>> genoarray_concordance(g([AA,AB,AB,BB,NN,BB]),g([NN,AA,AB,AB,BB,NN]))
  (1, 3)

  Test odd number of genotypes

  >>> descr = GenotypeArrayDescriptor([model]*7)

  >>> genoarray_concordance(g([NN,AA,AB,AB,BB,NN,AB]),g([NN,AA,AB,AB,BB,NN,AB]))
  (5, 5)
  >>> genoarray_concordance(g([NN,NN,NN,NN,NN,NN,NN]),g([NN,AA,AB,AB,BB,NN,AB]))
  (0, 0)
  >>> genoarray_concordance(g([NN,AA,AB,AB,BB,NN,AA]),g([NN,NN,NN,NN,NN,NN,NN]))
  (0, 0)
  >>> genoarray_concordance(g([AA,AB,AB,BB,NN,BB,AB]),g([NN,AA,AB,AB,BB,NN,BB]))
  (1, 4)

  Test fractions of a byte

  >>> descr = GenotypeArrayDescriptor([model]*1)
  >>> genoarray_concordance(g([AA]),g([AA]))
  (1, 1)
  >>> descr = GenotypeArrayDescriptor([model]*2)
  >>> genoarray_concordance(g([AA,AB]),g([AA,BB]))
  (1, 2)
  >>> descr = GenotypeArrayDescriptor([model]*3)
  >>> genoarray_concordance(g([AA,AB,BB]),g([AA,BB,AA]))
  (1, 3)
  >>> descr = GenotypeArrayDescriptor([model]*4)
  >>> genoarray_concordance(g([AA,AB,BB,AA]),g([AA,BB,AA,BB]))
  (1, 4)
  >>> descr = GenotypeArrayDescriptor([model]*5)
  >>> genoarray_concordance(g([AA,AB,BB,AA,AA]),g([AA,BB,AA,BB,AA]))
  (2, 5)
  '''


def main():
  import time
  import genoarray

  from   itertools import izip,repeat,imap
  from   operator  import getitem

  def parse_geno(g):
    g = g.strip()
    if not g:
      return None,None
    if len(g) == 1:
      return None,g
    else:
      return tuple(g)

  n = 500
  m = 5000

  genos = ['AA','AC','CC','AA','CA','',' A','C ']*m

  t1 = time.clock()

  if 1:
    model   = model_from_alleles('ACGT',allow_hemizygote=True)
    descr   = GenotypeArrayDescriptor( [model]*len(genos) )
    genomap = dict( (g,m.get_genotype(parse_geno(g))) for m,g in izip(descr.models,genos) )
    print descr.bit_size,descr.byte_size, float(descr.bit_size)/len(descr)

  if 1:
    for i in range(n):
      e = GenotypeArray(descr, imap(getitem, repeat(genomap), genos))
      f = GenotypeArray(e, e)
      d = map(Genotype.alleles, e)

  t2 = time.clock()

  if 1:
    for i in range(n):
      e = genoarray.snp_acgt2.pack_strs(genos)
      f = genoarray.snp_acgt2.pack_reps(e)
      d = genoarray.snp_acgt2.genos_from_reps(e)

  t3 = time.clock()

  if 1:
    for i in range(n):
      e = genoarray.snp_acgt.pack_strs(genos)
      f = genoarray.snp_acgt.pack_reps(e)
      d = genoarray.snp_acgt.genos_from_reps(e)

  t4 = time.clock()

  if 1:
    for i in range(m):
      e = genoarray.snp_marker.pack_strs(genos)
      f = genoarray.snp_marker.pack_reps(e)
      d = genoarray.snp_marker.genos_from_reps(e)

  t5 = time.clock()

  if 1:
    print '_genoarray:',t2-t1
    print 'snp_acgt2 :',t3-t2
    print 'snp_acgt  :',t4-t3
    print 'snp_marker:',t5-t4
    print
    print '_genoarray/snp_acgt  :',(t2-t1)/(t4-t3),(t4-t3)/(t2-t1)
    print 'snp_acgt2 /snp_acgt  :',(t3-t2)/(t4-t3),(t4-t3)/(t3-t2)
    print
    print 'snp_acgt2 /snp_marker:',(t3-t2)/(t5-t4),(t5-t4)/(t3-t2)
    print '_genoarray/snp_marker:',(t2-t1)/(t5-t4),(t5-t4)/(t2-t1)

  if 0:
    snp_ab = model_from_alleles('AB',allow_hemizygote=True)
    print snp_ab.bit_size
    print snp_ab.alleles
    print snp_ab.genotypes
    print snp_ab.genomap

  if 0:
    print len(snp_ab.get_genotype( (None,None) ) )
    print len(snp_ab.get_genotype( ('A',None)  ) )
    print len(snp_ab.get_genotype( (None,'A')  ) )
    print len(snp_ab.get_genotype( ('A', 'A')  ) )
    print bool(snp_ab.get_genotype( (None,None) ) )
    print bool(snp_ab.get_genotype( ('A',None)  ) )
    print bool(snp_ab.get_genotype( (None,'A')  ) )
    print bool(snp_ab.get_genotype( ('A', 'A')  ) )
    print 'A'  in snp_ab.get_genotype( (None,None) )
    print 'A'  in snp_ab.get_genotype( ('A',None)  )
    print 'A'  in snp_ab.get_genotype( (None,'A')  )
    print 'A'  in snp_ab.get_genotype( ('A', 'A')  )
    print 'B'  in snp_ab.get_genotype( (None,None) )
    print 'B'  in snp_ab.get_genotype( ('A',None)  )
    print 'B'  in snp_ab.get_genotype( (None,'A')  )
    print 'B'  in snp_ab.get_genotype( ('A', 'A')  )
    print None in snp_ab.get_genotype( (None,None) )
    print None in snp_ab.get_genotype( ('A',None)  )
    print None in snp_ab.get_genotype( (None,'A')  )
    print None in snp_ab.get_genotype( ('A', 'A')  )
    print snp_ab.get_genotype( (None,None) )[0],snp_ab.get_genotype( (None,None) )[1]
    print snp_ab.get_genotype( ('A',None)  )[0],snp_ab.get_genotype( ('A',None)  )[1]
    print snp_ab.get_genotype( (None,'A')  )[0],snp_ab.get_genotype( (None,'A')  )[1]
    print snp_ab.get_genotype( ('A', 'A')  )[0],snp_ab.get_genotype( ('A', 'A')  )[1]

  if 0:
    genos = ['AA','AA','','BB','BA','AA']
    print snp_ab.genotypes
    descr = GenotypeArrayDescriptor( [snp_ab]*len(genos) )
    e = GenotypeArray(descr, (parse_geno(g) for g in genos))
    print descr.byte_size
    print e
    print e.data
    print buffer(e.data)


def test():
  import doctest
  return doctest.testmod()


if __name__ == '__main__':
  test()

  if 0:
    if 0:
      try:
        import cProfile as profile
      except ImportError:
        import profile
      import pstats

      prof = profile.Profile()
      try:
        prof.runcall(main)
      finally:
        stats = pstats.Stats(prof)
        stats.strip_dirs()
        stats.sort_stats('time', 'calls')
        stats.print_stats(25)
    else:
      main()
