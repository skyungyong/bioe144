import Bio
from Bio import SeqIO
from Bio import AlignIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
from Bio.Alphabet import IUPAC
from Bio.Blast import NCBIXML
from Bio.Blast.NCBIWWW import qblast
from Bio.Align.Applications import MafftCommandline
from Bio.Align import MultipleSeqAlignment
from Bio import Phylo 
import os
import dendropy
import re



#Ensures environment variables are set
assert os.environ.get("BLASTDB")!=None, "Directory of Blast database must be set"

#Set path to BLAST home (Default install location)
if not os.environ["PATH"]:
    os.environ["PATH"] = "$HOME/ncbi-blast-2.2.29+/bin"


#Yields a list of topological annotations for each item in the text file
class Residue:
    def __init__(self,annotation,aa):
        self.annotation = annotation
        self.aa = aa
#Data structure to represent the a sequence of Residues/indels
class Sequence:
    def __init__(self,identifier):
        self.sequence = [] #Linked list may have been better data structure, allows for insertion and deletion in constant time
        self.id = identifier
    def __len__(self):
        return len(self.sequence)
    def __getitem__(self, item):
        return self.sequence[item]
    def __repr__(self):
        output = ""
        for item in self.sequence:
            output += item.aa
        return output



#OPERATING PROCESSES
E_VAL_THRESH = .005
ALIGN_PERCENT_THRESH = 70
DATABASE = "nr.61"
CONSENSUS_THRESH = .5
INPUT_SEQUENCE = "operating_reqs/fasta.txt"
save_file_name = "operating_reqs/alignment.xml"
recs_file = "operating_reqs/records.fasta"
tree_file = 'operating_reqs/tree_files/RAxML_bestTree.ML_out'
tmhmm_file='operating_reqs/tmhmm.html'


def length(fasta):
    input = SeqIO.read(fasta,format="fasta")
    return len(input)


input_len = length(INPUT_SEQUENCE)

#
# """Uses BioPython rather than System os"""
# def gather_homologs(fasta): #File location passed as input ("fasta.txt")
#     blasted = NcbiblastpCommandline(query=fasta,db="nr.61",evalue=1,outfmt=5,out="alignment.xml")
#     blasted()


"""Using System os
-qcov_hsp_perc allows for a defined query coverage """
def sys_gather_homologs(fasta):
    generic = "blastp -db {0} -query {1} -evalue {2}" \
              " -outfmt {3} -out {4} -qcov_hsp_perc {5}"
    db=DATABASE
    query = fasta
    evalue = E_VAL_THRESH #Change if wanted
    outfmt = 5 # Indicates BLAST XML to write to file
    out = save_file_name #Data written to alignment.xml
    query_coverage = ALIGN_PERCENT_THRESH #Minimum required overlap
    formatted = generic.format(db,query,evalue,outfmt,out,query_coverage)
    os.system(formatted)


#raxml --> phyML
#neighbor joining --> protdist



def parse_xml(): #This is alignment.xml
    with open(save_file_name) as result_handle:
        blast_record = NCBIXML.read(result_handle)
    recs = []
    i = 0
    for alignment in blast_record.alignments:
        for hsp in alignment.hsps:
            filtered_seq = Seq(str(hsp.sbjct), IUPAC.protein)
            filtered_id = alignment.title.split("|")[3]
            filtered_name = alignment.title
            filtered_seqrec = SeqRecord(filtered_seq, id=filtered_id, name=filtered_name)
            recs.append(filtered_seqrec)
    _ = SeqIO.write(recs, recs_file, "fasta")
    print("Done")

def generate_msa():
    mafft_cline = MafftCommandline(input=recs_file)
    stdout, stderr = mafft_cline()
    with open(recs_file, "w") as handle:
        handle.write(stdout)


def msaprocess(): #Takes an input from the generate_msa function
    processed = SeqIO.parse(recs_file,"fasta")
    output = [] #Returns a list of homologs all with TMH annotations
    helices = parse_TMHMM()
    for record in processed:
        identifier = record.name
        annotation = helices[identifier][1]
        membrane = topology(annotation)
        gapped_sequence = str(record.seq)
        representation = generate_rep(gapped_sequence,membrane,identifier)
        output.append(representation)
    return output

def parse_TMHMM():
    TMHMM_results = {}
    with open(tmhmm_file) as TMHMM_results_file:
        all_preds = TMHMM_results_file.read().split('\n')
    for pred in all_preds:
        pred = pred.split('\t')
        pred_id = pred[0]
        pred_len = eval(pred[1][pred[1].index("=")+1:])
        pred_hel_num = eval(pred[4][pred[4].index("=")+1:])
        pred_topo = pred[5][pred[5].index("=")+1:]
        TMHMM_results[pred_id] = (pred_hel_num, pred_topo, pred_len)
    return TMHMM_results
    #Now TMHMM Results are set as id:(pred_hel_number,pred_topo,pred_len)


def topology(annotation):#Parses the TMHMM String
    output = [] # A list of tuples with start,end,annotation
    processed = annotation.replace("-",":").replace("o","] [").replace("i","] [").split(" ")[1:-1]
    for item in processed:
        item = item.strip("[").strip("]").split(":")
        start = int(item[0])
        end = int(item[1])
        check = item[0] + '-' + item[1]
        notation = annotation[annotation.index(check)-1]
        output.append((start,end,notation))
        print((start,end,notation))
    return output


def generate_rep(sequence,topology,identifier):
    overall = Sequence(identifier)
    gaps = []
    for i in range(len(sequence)):
        if (sequence[i] == "-"):
            gaps.append(i) #Maintain positions of gaps

    #Remove all gaps
    sequence = re.sub(r"-","",sequence)

    #Initialize each protein without annotations
    for item in sequence:
        x = Residue("",item)
        overall.sequence.append(x)

    #Annotate each protein
    for item in topology:
        start = item[0]
        end = item[1]
        annotation = item[2]
        for i in range(start-1,end):
            overall.sequence[i].annotation = annotation

    #Reinsert gap characters
    gap = Residue("","-")
    for index in gaps:
        overall.sequence.insert(index,gap)

    return overall


"""Note specific columns can be removed using the argument
    -- select {{n,l,m-k}}
    Masks and edits the alignment intelligently.
"""
def mask_msa(): #DON"T MASK UNTIL AFTER MSA_PROCESS()!
    terminal_source = "trimal -automated1 -in {0} -out {1}"
    os.system(terminal_source.format(recs_file,recs_file))



"""Uses RaxML to generate tree which is read out by Bio's Phylo module"""
def generate_tree_RAxML():
    directory = os.getcwd()
    #Delete all existing tree files 
    os.system("rm {0}/*".format(directory + '/operating_reqs/tree_files'))
    command = 'raxmlHPC -s {0} -m {1} \
            -p {2} -n ML_out -# {3} -w {4}'
    sequence_file_name = directory + '/' + recs_file
    substitution_model = "PROTCATDAYHOFF" 
    parsinomy_random_seed = "1000"
    num_runs = "1"
    write_file = directory + '/' + 'operating_reqs/tree_files' 
    os.system(command.format(sequence_file_name,
        substitution_model,parsinomy_random_seed,
        num_runs, write_file))
    tree = Phylo.read(tree_file, 'newick')
    Phylo.draw_ascii(tree)
    return tree 

def generate_tree_phyml():
    pass #This is loaded in a separate file in case




def distances(input):
    tree = dendropy.Tree.get(
        path=tree_file,
        schema="newick"
    )
    pdm = tree.phylogenetic_distance_matrix()
    for idx1, taxon1 in enumerate(tree.taxon_namespace):
        for taxon2 in tree.taxon_namespace:
            mrca = pdm.mrca(taxon1, taxon2)
            weighted_patristic_distance = pdm.patristic_distance(taxon1, taxon2)
            unweighted_patristic_distance = pdm.path_edge_count(taxon1, taxon2)


#Sifter bayesian phylogenetic approach
#gene ontology annotations



"""Runs the entire phylogenetic process with RAxML"""
def run():
    sys_gather_homologs(INPUT_SEQUENCE)
    parse_xml()
    generate_msa()
    mask_msa()
    generate_tree_RAxML()







