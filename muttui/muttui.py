#Runs the MutTui pipeline on an input tree and alignment

import os
import argparse
from isvalid import *
from treetime import run_treetime
import subprocess
from Bio import AlignIO, Phylo
from collections import OrderedDict
from branch_labelling import *
from reconstruct_spectrum import *

from __init__ import __version__

#Parse command line options
def get_options():
    description = "Run the MutTui pipeline on a given alignment and tree"

    parser = argparse.ArgumentParser(description = description)

    #Options for input and output files
    io_opts = parser.add_argument_group("Input/output")
    io_opts.add_argument("-a",
                        "--alignment",
                        dest = "alignment",
                        required = True,
                        help = "Input fasta alignment",
                        type = argparse.FileType("r"))
    io_opts.add_argument("-t",
                        "--tree",
                        dest = "tree",
                        required = True,
                        help = "Newick tree file",
                        type = argparse.FileType("r"))
    io_opts.add_argument("-o",
                        "--out_dir",
                        dest = "output_dir",
                        required = True,
                        help = "Location of output directory, should already be created and ideally be empty",
                        type = lambda x: is_valid_folder(parser, x))
    io_opts.add_argument("-l",
                        "--labels",
                        dest = "labels",
                        help = "Comma separated file with sequences and their clade labels to divide the spectrum. " +
                        "If this option is included, treetime mugration will be run to identify changes in the label across the tree. " +
                        "Does not need to include all taxa. Taxa not included will be given a label of OTHER by default, " +
                        "or OTHER_A if OTHER is already taken. This file should have a header.",
                        default = None)
    io_opts.add_argument("-lt",
                        "--labelled_tree",
                        dest = "labelled_tree",
                        help = "Tree with state labels, should be the same tree as that provided with -t but with nodes " + 
                        "labelled with their state from label_tree.py",
                        default = None,
                        type = argparse.FileType("r"))
    io_opts.add_argument("-r",
                        "--reference",
                        dest = "reference",
                        help = "Reference genome sequence containing all sites, used to get context of mutations, not required if using --all_sites",
                        type = argparse.FileType("r"),
                        default = None)
    io_opts.add_argument("-c",
                        "--conversion",
                        dest = "conversion",
                        help = "Conversion file for alignment position to genome position, used to get context of mutations, not required if using --all_sites",
                        type = argparse.FileType("r"),
                        default = None)
    io_opts.add_argument("-s",
                        "--spectra_to_combine",
                        dest = "spectra_to_combine",
                        help = "Optional file containing labels whose spectra will be combined. " + 
                        "The spectra of these labels will be calculated independently and then combined post-processing. " + 
                        "For example, label each patient separately to calculate mutations within a patient clade, then combine " + 
                        "the spectra from multiple patients into a single within-patient spectrum. This file has no header. Each row " + 
                        "is a set of labels to be combined separated by commas",
                        type = argparse.FileType("r"),
                        default = None)
    
    #Options to include in treetime reconstruction
    treetime = parser.add_argument_group("treetime command")
    treetime.add_argument("--add_treetime_cmds",
                        dest = "add_treetime_cmds",
                        help = "Additional options to supply to treetime (these are not checked). Supply these together in quotes",
                        type = str,
                        default = None)
    
    #Other options
    parser.add_argument("--rna",
                        dest = "rna",
                        help = "Specify if using an RNA pathogen, MutTui will output an RNA mutational spectrum",
                        action = "store_true",
                        default = False)
    parser.add_argument("--all_sites",
                        dest = "all_sites",
                        help = "Specify that the alignment contains all sites, in which case a reference genome does not need to be provided",
                        action = "store_true",
                        default = False)
    parser.add_argument("-rs",
                        "--root_state",
                        dest = "root_state",
                        help = "Specify the root state of the given label if known. " + 
                        "The root state is calculated by treetime mugration and in almost all cases will be resolved. " + 
                        "If the root state has multiple assignments that are equally likely, it cannot be assigned from " + 
                        "treetime mugration output. In these rare cases, use this option to assign the root state. This option " + 
                        "can also be used to assign a root state if you'd like but its recommended to use the mugration state",
                        default = None)
    parser.add_argument("--version",
                        action = "version",
                        version = "%(prog)s " + __version__)
    
    args = parser.parse_args()
    return(args)

def main():
    args = get_options()

    #Make sure trailing forward slash is present in output directory
    args.output_dir = os.path.join(args.output_dir, "")

    #Open output files
    outMutationsNotUsed = open(args.output_dir + "mutations_not_included.csv", "w")
    outMutationsNotUsed.write("Mutation_in_alignment,Mutation_in_genome,Branch,Reason_not_included\n")

    outAllMutations = open(args.output_dir + "all_included_mutations.csv", "w")
    outAllMutations.write("Mutation_in_alignment,Mutation_in_genome,Branch\n")

    print("Running treetime ancestral reconstruction to identify mutations")

    #Run treetime on the input alignment and tree with any provided options
    run_treetime(args.alignment, args.tree, args.output_dir, args.add_treetime_cmds)

    #Import the alignment and tree from treetime
    alignment = AlignIO.read(args.output_dir + "ancestral_sequences.fasta", "fasta")
    tree = Phylo.read(args.output_dir + "annotated_tree.nexus", "nexus")

    #Label branches in the tree into categories, each category will have a separate spectrum
    if args.labels:
        #Extract the labels to a dictionary and add taxa without a label
        labelDict = getLabelDict(tree, args.labels)

        #Write the labels to a csv that can be used by treetime mugration
        writeLabels(labelDict, args.output_dir)

        #Run treetime mugration to reconstruct the clade labels across the tree
        run_treetime_mugration(args.output_dir + "annotated_tree.nexus", args.output_dir + "all_taxon_labels.csv", args.output_dir)

        #Import the files from treetime mugration
        mugrationTree = Phylo.read(args.output_dir + "mugration_out/annotated_tree.nexus", "nexus")
        confidence = open(args.output_dir + "mugration_out/confidence.csv").readlines()
        gtr = open(args.output_dir + "mugration_out/GTR.txt").readlines()

        #Identify the root state and add it to the mugrationTree
        mugrationTree = rootState(mugrationTree, confidence, gtr, args.root_state)

        labelledTree, treeLabels = labelBranchesMugration(tree, mugrationTree)
    elif args.labelled_tree:
        labelledTree, treeLabels = getLabelledTreeLabels(tree, args.labelled_tree)
    else:
        labelledTree, treeLabels = labelAllBranches(tree)
    
    #Branch categories as keys, spectra as values
    spectraDict = {}
    #Create empty spectrum for each branch category
    if args.rna:
        for label in treeLabels:
            spectraDict[label] = getRNADict()
    else:
        for label in treeLabels:
            spectraDict[label] = getMutationDict()
    
    #The 4 nucleotides, used to check if mutated, upstream and downstream bases are nucleotides
    nucleotides = ["A","C","G","T"]

    #Convert the positions in the alignment to genome positions, if --all_sites specified the positions will be the same
    if args.all_sites:
        positionTranslation = allSitesTranslation(alignment)
    else:
        positionTranslation = convertTranslation(args.conversion)
    
    #Extract mutations to dictionary with branches as keys and mutations as values
    branchMutationDict = getBranchDict(labelledTree, positionTranslation)

    #Get the reference sequence, if -r specified this will be the provided genome, otherwise all sites in the alignment are assumed
    #and the root sequence from the ancestral reconstruction is used
    referenceSequence = getReference(args.reference, args.all_sites, alignment, positionTranslation)
    referenceLength = len(referenceSequence)
    
    #Iterate through the branches, get the category of the branch, identify the contextual mutations, add to the corresponding spectrum
    for clade in labelledTree.find_clades():
        #Do not analyse the root
        if len(tree.get_path(clade)) != 0:
            #Identify the name of the branch
            branchName = getBranchName(tree, clade)

            branchCategory = getBranchCategory(labelledTree, clade)

            #Check if there are mutations along the branch, the .comment is only added to the clade if there are
            #Check if the branch has a category, will be none if the branch is a transition between categories
            if clade.comment and (branchCategory is not None):
                branchMutations = branchMutationDict[branchName]

                #Check if there are double substitutions along the branch and remove these mutations
                if len(branchMutations) > 1:
                    positionsToRemove = []
                    for mutation1 in range(0, (len(branchMutations) - 1)):
                        for mutation2 in range((mutation1 + 1), len(branchMutations)):
                            if branchMutations[mutation2][2] == (branchMutations[mutation1][2] + 1):
                                positionsToRemove.append(mutation1)
                                positionsToRemove.append(mutation2)
                    if len(positionsToRemove) != 0:
                        #Write the positions to the mutations not analysed file
                        for removePosition in positionsToRemove:
                            outMutationsNotUsed.write(branchMutations[removePosition][0] + str(branchMutations[removePosition][1]) + branchMutations[removePosition][3] + "," + branchMutations[removePosition][0] + str(branchMutations[removePosition][2]) + branchMutations[removePosition][3] + "," + branchName + ",Double_substitution\n")
                        #Remove the positions from the mutations
                        for ele in sorted(positionsToRemove, reverse = True):
                            del branchMutations[ele]
                
                #Update the reference sequence to get the current context
                updatedReference = updateReference(tree, clade, branchMutationDict, referenceSequence)

                for mutation in branchMutations:
                    #Check if the mutation is at the end of the genome, if it is it does not have context so cannt be analysed
                    if (mutation[2] == 1) or (mutation[2] == referenceLength):
                        outMutationsNotUsed.write(mutation[0] + str(mutation[1]) + mutation[3] + "," + mutation[0] + str(mutation[2]) + mutation[3] + "," + branchName + ",End_of_genome\n")
                    #Check if the mutation does not involve 2 nucleotides
                    elif (mutation[0] not in nucleotides) or (mutation[3] not in nucleotides):
                        outMutationsNotUsed.write(mutation[0] + str(mutation[1]) + mutation[3] + "," + mutation[0] + str(mutation[2]) + mutation[3] + "," + branchName + ",Mutation_does_not_involve_two_nucleotides\n")
                    else:
                        mutationContext = getContext(mutation, updatedReference)
                    
                        #Check if the upstream or downstream nucleotides are not A, C, G or T
                        if (mutationContext[0] not in nucleotides) or (mutationContext[1] not in nucleotides):
                            outMutationsNotUsed.write(mutation[0] + str(mutation[1]) + mutation[3] + "," + mutation[0] + str(mutation[2]) + mutation[3] + "," + branchName + ",Surrounding_position_not_nucleotide\n")
                        else:
                            #This will be true for all RNA mutations and half of DNA mutations
                            if (mutationContext[0] + mutation[0] + mutation[3] + mutationContext[1]) in spectraDict[branchCategory]:
                                spectraDict[branchCategory][mutationContext[0] + mutation[0] + mutation[3] + mutationContext[1]] += 1
                                outAllMutations.write(mutation[0] + str(mutation[1]) + mutation[3] + "," + mutation[0] + str(mutation[2]) + mutation[3] + "," + branchName + "\n")
                            #Add to the corresponding complement
                            else:
                                spectraDict[branchCategory][complement(mutationContext[1]) + complement(mutation[0]) + complement(mutation[3]) + complement(mutationContext[0])] += 1
                                outAllMutations.write(complement(mutation[0]) + str(mutation[1]) + complement(mutation[3]) + "," + complement(mutation[0]) + str(mutation[2]) + complement(mutation[3]) + "," + branchName + "\n")
    
    #Write the spectra to separate files
    for eachLabel in spectraDict:
        outFile = open(args.output_dir + "mutational_spectrum_label_" + eachLabel + ".csv", "w")
        #outFileCatalog = open(args.output_dir + "catalog_label_" + eachLabel + ".csv", "w")
        outFile.write("Substitution,Number_of_mutations\n")
        for eachMutation in spectraDict[eachLabel]:
            outFile.write(eachMutation[0] + "[" + eachMutation[1] + ">" + eachMutation[2] + "]" + eachMutation[3] + "," + str(spectraDict[eachLabel][eachMutation]) + "\n")
        outFile.close()

    #Close output files
    outMutationsNotUsed.close()
    outAllMutations.close()

if __name__ == "__main__":
    main()