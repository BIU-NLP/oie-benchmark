""" Usage:
    qa_to_oie --in=INPUT_FILE --out=OUTPUT_FILE [--oieinput=OIE_INPUT]
"""

from docopt import docopt
import re
import itertools
from oie_readers.extraction import Extraction, escape_special_chars
from collections  import defaultdict
import logging
import operator

## CONSTANTS

QUESTION_TRG_INDEX =  3 # index of the predicate within the question
QUESTION_MODALITY_INDEX = 1 # index of the modality within the question
PASS_ALL = lambda x: x
MASK_ALL = lambda x: "_"
get_default_mask = lambda : [PASS_ALL] * 8


class Qa2OIE:
    
    # Static variables
    extractions_counter = 0
    
    def __init__(self, qaFile):
        ''' loads qa file and converts it into  open IE '''
        self.dic = self.loadFile(self.getExtractions(qaFile))
    
    def loadFile(self, lines):
        sent = ''
        d = {}

        indsForQuestions = defaultdict(lambda: set())
                
        for line in lines.split('\n'):
            line = line.strip()
            if not line:
                continue
            data = line.split('\t')
            if len(data) == 1:
                if sent:
                    for ex in d[sent]:
                        ex.indsForQuestions = dict(indsForQuestions)
                sent = line
                d[sent] = []
                indsForQuestions = defaultdict(lambda: set())
                
            else:
                pred = data[0]
                cur = Extraction((pred, all_index(sent, pred, matchCase = False)), sent, confidence = 1.0)
                for q, a in zip(data[1::2], data[2::2]):
                    indices = all_index(sent, a, matchCase = False)
                    cur.addArg((a, indices), q)
                    indsForQuestions[q] = indsForQuestions[q].union(indices)

                if sent:
                    if cur.noPronounArgs():
                        d[sent].append(cur)
        return d
    
    def getExtractions(self, qa_srl_path, mask = get_default_mask()):
        qa_input = open(qa_srl_path, 'r')
        lc = 0
        curArgs = []
        sentQAs = []
        curPred = ""
        curSent = ""
        ret = ''
        
        for line in qa_input:
            line = line.strip()
            info = line.strip().split("\t")
            if lc == 0:
                # Read sentence ID.
                sent_id = int(info[0].split("_")[1])
                ptb_id = []
                lc += 1
            elif lc == 1:
                if curSent:
                    ret += self.printSent(curSent, sentQAs)
                # Write sentence.
                curSent = line
                lc += 1
                sentQAs = []
            elif lc == 2:  
                if curArgs: 
                    sentQAs.append((curPred, curArgs))
                    curArgs = []
                # Update line counter.
                if line.strip() == "":
                    lc = 0 # new line for new sent
                else:
                    # reading predicate and qa pairs
                    curPred, count = info[1:]
                    lc += int(count)
            elif lc > 2:
                question = encodeQuestion("\t".join(info[:-1]), mask)
                answers = self.consolidate_answers(info[-1].split("###"))
                curArgs.append(zip([question]*len(answers), answers))
                lc -= 1
        if sentQAs:
            ret += self.printSent(curSent, sentQAs)
        qa_input.close()
        return ret
        
    def printSent(self, sent, sentQAs):
        ret =  sent + "\n"
        for pred, predQAs in sentQAs:
            for element in itertools.product(*predQAs):
                self.encodeExtraction(element)
                ret += "\t".join([pred] + ["\t".join(x) for x in element]) + "\n"
        ret += "\n"  
        return ret
        
    def encodeExtraction(self, element):
        questions = map(operator.itemgetter(0),element)
        extractionSet = set(questions)
        encoding = repr(extractionSet)
        (count, _, extractions) = extractionsDic.get(encoding, (0, extractionSet, []))
        extractions.append(Qa2OIE.extractions_counter)
        Qa2OIE.extractions_counter += 1
        extractionsDic[encoding] = (count+1, extractionSet, extractions)

        
    def consolidate_answers(self, answers):
        ret = []
        for i, first_answer in enumerate(answers):
            includeFlag = True
            for j, second_answer in enumerate(answers):
                if (i != j) and (is_str_subset(second_answer, first_answer)) :
                    includeFlag = False
                    continue
            if includeFlag:
                ret.append(first_answer)
        return ret
    
    def createOIEInput(self, fn):
        with open(fn, 'a') as fout:
            for sent in self.dic:
                fout.write(sent + '\n')
                
    def writeOIE(self, fn):
        with open(fn, 'w') as fout:
            for sent, extractions in self.dic.iteritems():
                for ex in extractions:
                    fout.write('{}\t{}\n'.format(escape_special_chars(sent), 
                                                 ex.__str__()))
    
# MORE HELPER 

def is_str_subset(s1, s2):
    """ returns true iff the words in string s1 are contained in string s2 in the same order by which they appear in s2 """
    all_indices = [find_all_indices(s2.split(" "), x) for x in s1.split()]
    if not all(all_indices):
        return False
    for combination in itertools.product(*all_indices):
        if strictly_increasing(combination):
            return True
    return False

def find_all_indices(ls, elem):
    return  [i for i,x in enumerate(ls) if x == elem]

def strictly_increasing(L):
    return all(x<y for x, y in zip(L, L[1:]))


questionsDic = {}
extractionsDic = {}


def encodeQuestion(question, mask):
    info = [mask[i](x).replace(" ","_") for i,x in enumerate(question.split("\t"))]
    encoding = "\t".join(info)
    (val, count) = questionsDic.get(encoding, (len(questionsDic), 0)) # get the encoding of a question, and the count of times it appeared
    questionsDic[encoding] = (val, count+1)
    # remove underscores just for better readability
#     ret = '{0}'.format(" ".join([x for x in info if x != "_"]))  
    ret = " ".join(info)  
    return ret



def all_index(s, ss, matchCase = True, ignoreSpaces = True):
    ''' find all occurrences of substring ss in s '''
    if not matchCase:
        s = s.lower()
        ss = ss.lower()
        
    if ignoreSpaces:
        s = s.replace(' ', '')
        ss = ss.replace(' ','')
    
    return [m.start() for m in re.finditer(re.escape(ss), s)]

def longest_common_substring(s1, s2):
    m = [[0] * (1 + len(s2)) for i in xrange(1 + len(s1))]
    longest, x_longest = 0, 0
    for x in xrange(1, 1 + len(s1)):
        for y in xrange(1, 1 + len(s2)):
            if s1[x - 1] == s2[y - 1]:
                m[x][y] = m[x - 1][y - 1] + 1
                if m[x][y] > longest:
                    longest = m[x][y]
                    x_longest = x
            else:
                m[x][y] = 0
                
    start = x_longest - longest
    end = x_longest
    
    return s1[start:end]

## MAIN 
if __name__ == '__main__':
    logging.basicConfig(level = logging.CRITICAL)
    args = docopt(__doc__)
    logging.debug(args)
    q = Qa2OIE(args['--in'])
    q.writeOIE(args['--out'])
    if args['--oieinput']:
        q.createOIEInput(args['--oieinput'])

             
