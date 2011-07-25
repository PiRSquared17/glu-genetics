# -*- coding: utf-8 -*-

from __future__ import division

__gluindex__  = True
__abstract__  = 'Filter SAM/BAM files'
__copyright__ = 'Copyright (c) 2010, BioInformed LLC and the U.S. Department of Health & Human Services. Funded by NCI under Contract N01-CO-12400.'
__license__   = 'See GLU license for terms by running: glu license'
__revision__  = '$Id$'


import sys

from   collections           import deque
from   operator              import attrgetter, itemgetter
from   itertools             import groupby, imap

import pysam

from   glu.lib.utils         import consume
from   glu.lib.fileutils     import autofile, hyphen, list_reader
from   glu.lib.progressbar   import progress_loop

from   glu.lib.seqlib.bed    import read_features
from   glu.lib.seqlib.filter import alignment_filter_options, filter_alignments


STATUS_COUNT = 5
ONTARGET,OFFTARGET,UNALIGNED,TOOSHORT,CONTROL = range(STATUS_COUNT)


def set_readgroup(groupname,header,aligns):
  RG = header.get('RG')

  if not RG:
    header['RG'] = [{'ID':groupname,'PL':'unknown','SM':groupname}]
  else:
    RG[:] = RG[0:1]
    RG[0]['ID'] = RG[0]['SM'] = groupname

  # Return a nested generator, since header update must occur immediately
  def _set_readgroup():
    rg = ('RG',groupname)

    for align in aligns:
      tags = align.tags or []

      try:
        names,values = zip(*tags)
        idx = names.index('RG')
        tags[idx] = rg

      except ValueError:
        tags.append(rg)

      align.tags = tags

      yield align

  return _set_readgroup()


def simple_filter(aligns,controls,stats,options):
  minreadlen = options.minreadlen

  fail = options.action=='fail'

  reads_ONTARGET   = 0
  bases_ONTARGET   = 0
  lengs_ONTARGET   = stats.lengths[ONTARGET]
  reads_UNALIGNED  = 0
  bases_UNALIGNED  = 0
  lengs_UNALIGNED  = stats.lengths[UNALIGNED]
  reads_TOOSHORT   = 0
  bases_TOOSHORT   = 0
  lengs_TOOSHORT   = stats.lengths[TOOSHORT]
  reads_CONTROL    = 0
  bases_CONTROL    = 0
  lengs_CONTROL    = stats.lengths[CONTROL]

  try:
    for tid,contig_aligns in groupby(aligns, attrgetter('tid')):
      if tid<0:
        for align in contig_aligns:
          rlen = align.rlen

          reads_UNALIGNED       += 1
          bases_UNALIGNED       += rlen
          lengs_UNALIGNED[rlen] += 1

          if fail:
            align.is_qcfail = 1
            yield align

      elif tid in controls:
        for align in contig_aligns:
          rlen = align.rlen

          reads_CONTROL       += 1
          bases_CONTROL       += rlen
          lengs_CONTROL[rlen] += 1

          if fail:
            align.is_qcfail = 1
            yield align

      else:
        for align in contig_aligns:
          rlen = align.rlen

          if rlen<minreadlen:
            reads_TOOSHORT       += 1
            bases_TOOSHORT       += rlen
            lengs_TOOSHORT[rlen] += 1

            if fail:
              align.is_qcfail = 1
              yield align

          else:
            reads_ONTARGET       += 1
            bases_ONTARGET       += rlen
            lengs_ONTARGET[rlen] += 1

            yield align

  finally:
    stats.reads[ONTARGET]  += reads_ONTARGET
    stats.bases[ONTARGET]  += bases_ONTARGET
    stats.reads[UNALIGNED] += reads_UNALIGNED
    stats.bases[UNALIGNED] += bases_UNALIGNED
    stats.reads[TOOSHORT]  += reads_TOOSHORT
    stats.bases[TOOSHORT]  += bases_TOOSHORT
    stats.reads[CONTROL]   += reads_CONTROL
    stats.bases[CONTROL]   += bases_CONTROL


def target_filter(aligns,references,targets,controls,stats,options):
  contigs = set()

  minoverlap = options.minoverlap
  minreadlen = options.minreadlen
  nulltarget = sys.maxint,sys.maxint

  fail = options.action=='fail'

  reads_ONTARGET   = 0
  bases_ONTARGET   = 0
  lengs_ONTARGET   = stats.lengths[ONTARGET]
  reads_OFFTARGET  = 0
  bases_OFFTARGET  = 0
  lengs_OFFTARGET  = stats.lengths[OFFTARGET]
  reads_UNALIGNED  = 0
  bases_UNALIGNED  = 0
  lengs_UNALIGNED  = stats.lengths[UNALIGNED]
  reads_TOOSHORT   = 0
  bases_TOOSHORT   = 0
  lengs_TOOSHORT   = stats.lengths[TOOSHORT]
  reads_CONTROL    = 0
  bases_CONTROL    = 0
  lengs_CONTROL    = stats.lengths[CONTROL]

  try:
    for tid,contig_aligns in groupby(aligns, attrgetter('tid')):
      rname = references[tid] if tid>=0 else 'unaligned'

      ctargets = deque(targets.get(rname,[]))

      print >> sys.stderr, '[INFO] Processing contig=%s targets=%d' % (rname,len(ctargets))

      assert rname not in contigs, 'Duplicate contig %s seen' % rname
      contigs.add(rname)

      if rname=='unaligned':
        for align in contig_aligns:
          rlen = align.rlen

          reads_UNALIGNED       += 1
          bases_UNALIGNED       += rlen
          lengs_UNALIGNED[rlen] += 1

          if fail:
            align.is_qcfail = True
            yield align

        continue

      if tid in controls:
        for align in contig_aligns:
          rlen = align.rlen

          reads_CONTROL       += 1
          bases_CONTROL       += rlen
          lengs_CONTROL[rlen] += 1

          if fail:
            align.is_qcfail = True
            yield align

        continue

      next_start,next_end = ctargets[0][:2] if ctargets else nulltarget

      for align in contig_aligns:
        rlen = align.rlen

        # Fast-path 1: fail short aligns
        if rlen<minreadlen:
          reads_TOOSHORT       += 1
          bases_TOOSHORT       += rlen
          lengs_TOOSHORT[rlen] += 1

          if fail:
            align.is_qcfail = True
            yield align

          continue

        align_end = align.aend

        # Fast-path 2: No overlap with next target (if any)
        if align_end<next_start:
          reads_OFFTARGET       += 1
          bases_OFFTARGET       += rlen
          lengs_OFFTARGET[rlen] += 1

          if fail:
            align.is_qcfail = True
            yield align

          continue

        align_start = align.pos

        # Slow-path: Pop targets that end prior to the start of the current
        #            alignment.  This sets up the precondition no additional
        #            targets exist or that the next target begins at or before
        #            the currrent alignment start.
        while ctargets and next_end<align_start:
          ctargets.popleft()
          next_start,next_end = ctargets[0][:2] if ctargets else nulltarget

        # Compute overlap by iterating over targets until
        #   1: The current target starts after the end of the current
        #      alignment, which terminates the search.
        #   2: Otherwise, compute the amount overlap, which must be
        #      non-negative, and add it to the total overlap count.

        overlap_len = 0
        for target_start,target_end,target_name in ctargets:
          if target_start>align_end:
            break

          overlap_len += min(target_end,align_end)-max(target_start,align_start)

          # Determine if the degree of overlap is sufficient
          if overlap_len>=minoverlap:
            reads_ONTARGET       += 1
            bases_ONTARGET       += rlen
            lengs_ONTARGET[rlen] += 1

            yield align
            break

        else:
          reads_OFFTARGET       += 1
          bases_OFFTARGET       += rlen
          lengs_OFFTARGET[rlen] += 1

          if fail:
            align.is_qcfail = True
            yield align

  finally:
    stats.reads[ONTARGET]  += reads_ONTARGET
    stats.bases[ONTARGET]  += bases_ONTARGET
    stats.reads[OFFTARGET] += reads_OFFTARGET
    stats.bases[OFFTARGET] += bases_OFFTARGET
    stats.reads[UNALIGNED] += reads_UNALIGNED
    stats.bases[UNALIGNED] += bases_UNALIGNED
    stats.reads[TOOSHORT]  += reads_TOOSHORT
    stats.bases[TOOSHORT]  += bases_TOOSHORT
    stats.reads[CONTROL]   += reads_CONTROL
    stats.bases[CONTROL]   += bases_CONTROL


# UNUSED: This is a sanity-check implementation that uses an IntervalTree
#         data structure and does not require any assumptions about the
#         ordering of targets.
def target_filter_generic(aligns,references,targets,stats,options):
  from   glu.lib.seqlib.intervaltree  import IntervalTree

  contigs = set()
  minoverlap = options.minoverlap

  fail  = options.action=='fail'
  reads = stats.reads
  bases = stats.bases

  for tid,contig_aligns in groupby(aligns, attrgetter('tid')):
    rname = references[tid] if tid>=0 else 'unaligned'

    contig_targets = targets.get(rname,[])

    targettree = IntervalTree()
    for target_start,target_end,target_name in contig_targets:
      targettree.insert(target_start,target_end)

    print >> sys.stderr, '[INFO] Processing contig=%s targets=%d' % (rname,len(contig_targets))

    assert rname not in contigs, 'Duplicate contig %s seen' % rname
    contigs.add(rname)

    if rname=='unaligned':
      for align in contig_aligns:
        reads[UNALIGNED] += 1
        bases[UNALIGNED] += align.rlen

        if fail:
          align.is_qcfail = True
          yield align

      continue

    for align in contig_aligns:
      rlen = align.rlen

      if rlen<options.minreadlen:
        reads[TOOSHORT] += 1
        bases[TOOSHORT] += rlen

        if fail:
          align.is_qcfail = True
          yield align

        continue

      align_start = align.pos
      align_end   = align.aend

      overlap_len = 0
      for target in targettree.find(align_start, align_end):
        overlap_len += min(target.end,align_end)-max(target.start,align_start)

      if overlap_len<minoverlap:
        reads[OFFTARGET] += 1
        bases[OFFTARGET] += rlen

        if fail:
          align.is_qcfail = True
          yield align
      else:
        reads[ONTARGET] += 1
        bases[ONTARGET] += rlen
        yield align


class FilterStats(object):
  def __init__(self):
    self.reads   = [0]*STATUS_COUNT
    self.bases   = [0]*STATUS_COUNT
    self.lengths = [ [0]*6000 for i in range(STATUS_COUNT) ]


def sink_file(outbam,aligns):
  try:
    for align in aligns:
      outbam.write(align)

  finally:
    outbam.close()


def sink_null(aligns):
  consume(aligns)


def percent(a,b):
  return a/b*100 if b else 0


# UNUSED: Merging functionality was added to Pysam directly.  This code is
#         preserved for reference only.
def merge_bams(samfiles):
  from   copy                  import deepcopy
  from   glu.lib.imerge        import imerge
  from   glu.lib.utils         import chunk_iter

  header     = None
  references = None
  lengths    = None

  aligns     = []

  for samfile in samfiles:
    if references is None:
      references = samfile.references
    elif references != samfile.references:
      raise ValueError('Merging currently requires identical reference contigs')

    if lengths is None:
      lengths = samfile.lengths
    elif lengths != samfile.lengths:
      raise ValueError('Merging currently requires identical reference contigs lengths')

    if header is None:
      header = deepcopy(samfile.header)
    elif 'RG' in samfile.header:
      # FIXME: Assumes RGs are unique
      header.setdefault('RG',[]).extend(samfile.header['RG'])

    # Apply a read-ahead of 5000 alignments to minimize disk seeking at the
    # expense of a small amount of front-loaded latency
    aligns.append( chunk_iter(samfile.fetch(until_eof=True), 5000) )

  if len(aligns)>1:
    aligns = [ (((a.tid if a.tid>=0 else 99999)<<34|a.pos,a) for a     in align)
                                                             for align in aligns ]
    aligns = imap(itemgetter(1),imerge(aligns))
  else:
    aligns = aligns[0]

  return samfiles,header,references,lengths,aligns


def option_parser():
  import optparse

  usage = 'usage: %prog [options] in.bam'
  parser = optparse.OptionParser(usage=usage)

  alignment_filter_options(parser)

  parser.add_option('--minreadlen', dest='minreadlen', metavar='N', type='int', default=0,
                    help='Minimum read length filter')
  parser.add_option('--targets', dest='targets', metavar='BED',
                    help='Single track BED file containing all targeted intervals')
  parser.add_option('--controls', dest='controls', metavar='CONTIGS',
                    help='List of control contigs to allow those aligned '
                          'reads to be counted seperately from other aligned reads '
                          '(e.g.  PhiX controls)')
  parser.add_option('--minoverlap', dest='minoverlap', metavar='N', type='int', default=1,
                    help='Minimum alignment overlap with any target (default=1)')

  parser.add_option('--action', dest='action', metavar='X', default='fail',
                    help='Action to perform on failing alignments (drop or fail, default=fail)')

  parser.add_option('--setreadgroup', dest='setreadgroup', type='str', metavar='RGNAME',
                    help='Set all reads to specified read group name')
  parser.add_option('-o', '--output', dest='output', metavar='FILE',
                    help='Output BAM file')
  parser.add_option('-O', '--sumout', dest='sumout', metavar='FILE', default='-',
                    help='Summary output file')

  return parser


def main():
  parser = option_parser()
  options,args = parser.parse_args()

  if not args:
    parser.print_help(sys.stderr)
    sys.exit(2)

  options.action = options.action.lower()

  if options.action not in ('drop','fail'):
    raise ValueError('Invalid filter action selected')

  samfiles   = []
  for filename in args:
    flags   = 'rb' if filename.endswith('.bam') else 'r'
    samfiles.append(pysam.Samfile(filename, flags))

  if len(samfiles)==1:
    samfile    = samfiles[0]
    header     = samfile.header
    references = samfile.references
    lengths    = samfile.lengths
    aligns     = iter(samfile)

  elif 0: # Merging functionality is now part of our internal pysam tree
    samfiles,header,references,lengths,aligns = merge_bams(samfiles)

  else:
    merger     = pysam.SamMergeFiles(samfiles)
    header     = merger.header
    references = merger.references
    lengths    = merger.lengths
    aligns     = iter(merger)

  controls = set()
  if options.controls:
    rmap     = dict( (contig,tid) for tid,contig in enumerate(references) )
    controls = set(rmap.get(c) for c in set(list_reader(options.controls)))
    controls.discard(None)

  aligns = progress_loop(aligns, label='Loading BAM file(s): ', units='alignments')
  aligns = filter_alignments(aligns, options.includealign, options.excludealign)

  stats  = FilterStats()

  if options.targets:
    targets = read_features(options.targets)
    aligns  = target_filter(aligns,references,targets,controls,stats,options)
  else:
    aligns  = simple_filter(aligns,controls,stats,options)

  complete = False

  try:
    if options.output:
      if options.setreadgroup:
        aligns = set_readgroup(options.setreadgroup,header,aligns)

      flags  = 'wb' if options.output.endswith('.bam') else 'wh'

      outbam = pysam.Samfile(options.output, flags, header=header,
                                                    referencenames=references,
                                                    referencelengths=lengths)

      sink_file(outbam,aligns)
    else:
      sink_null(aligns)

    complete = True

  except KeyboardInterrupt:
    pass

  finally:
    for samfile in samfiles:
      samfile.close()

  bases   = stats.bases
  reads   = stats.reads
  lengths = stats.lengths

  total_reads = sum(reads)
  total_bases = sum(bases)

  sumout = autofile(hyphen(options.sumout, sys.stdout),'w')

  if complete:
    sumout.write('Alignment summary:\n')
  else:
    sumout.write('Partial alignment summary (execution interrupted):\n')

  def stat_line(status):
    return '%12d (%6.2f%%) %17d (%6.2f%%)' % (reads[status], percent(reads[status], total_reads),
                                              bases[status], percent(bases[status], total_bases))

  sumout.write('           STATUS       READS          %            BASES          %\n')
  for status,name in enumerate(['On-target','Off-target','Unaligned','Too short','Control']):
    sumout.write('  %15s: %s\n' % (name, stat_line(status)))

  if 0:
    sumout.write('\n\nREAD_LENGTH\tONTARGET_READS\tOFFTARGET_READS\tUNALIGNED_READS\tTOOSHORT_READS\tCONTROL\n')
    for i in xrange(len(lengths[0])):
      status_lengths = [ l[i] for l in lengths ]
      if sum(status_lengths):
        sumout.write('%d\t%s\n' % (i, '\t'.join(str(l) for l in status_lengths)))

  if not complete:
    raise KeyboardInterrupt


if __name__=='__main__':
  main()
