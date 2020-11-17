#Labels all branches in a given tree
#Takes a specified root state and the branches and state changes where the label changes
#Uses the node numbers from add_tree_node_labels.py to specify internal branches and the taxon IDs to specify tip branches

import argparse
from Bio import Phylo

#Labels the nodes and tips of the tree with their names
def labelAllClades(tree):
    #Will be incremented with each node
    nodeIterator = 1

    #Iterate through the clades and add labels
    for clade in tree.find_clades():
        if clade.is_terminal():
            clade.node_name = clade.name
        else:
            clade.node_name = "Node" + str(nodeIterator)
            nodeIterator += 1
    
    return(tree)

#Extracts dictionary from state changes, nodes as keys, states as values
def getStateDict(states):
    stateDict = {}

    for state in states:
        stateDict[state.split("____")[0]] = state.split("____")[1]
    
    return(stateDict)

#Gets the state of the upstream clade
def getParentState(tree, clade):
    #Check if the clade is one downstream of the root
    if len(tree.get_path(clade)) >= 2:
        nodeState = tree.get_path(clade)[-2].name
    else:
        nodeState = str(tree.root.name)
    
    return(nodeState)

#Labels each internal node and tip in a tree with their state
#Sets the root state to the provided root state and changes the state along specified branches
def labelTreeState(tree, root_state, stateDict):
    #Set the root state
    tree.root.name = root_state

    #Iterate through the clades, check if their state needs to be changed
    #otherwise use the state at the parent node
    for clade in tree.find_clades():
        #Do not analyse the root
        if len(tree.get_path(clade)) != 0:
            #Check if the state changes along the branch
            if clade.node_name in stateDict:
                if clade.is_terminal():
                    clade.name = clade.name + "____" + stateDict[clade.node_name]
                else:
                    clade.name = stateDict[clade.node_name]
            
            #Infer and keep the state at the parent node
            else:
                if clade.is_terminal():
                    clade.name = clade.name + "____" + getParentState(tree, clade)
                else:
                    clade.name = getParentState(tree, clade)
    
    return(tree)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-t",
                        "--tree",
                        dest = "tree",
                        required = True,
                        help = "Newick tree file",
                        type = argparse.FileType("r"))
    parser.add_argument("-r",
                        "--root_state",
                        dest = "root_state",
                        required = True,
                        help = "The state at the root of the tree. For example using -r A will set the state to A at the root")
    parser.add_argument("-s",
                        "--state_changes",
                        dest = "state_changes",
                        required = True,
                        nargs = "+",
                        help = "Branches and state changes. Give the name of the branch along which the state " + 
                        "change occured and the state at the end of the branch. Separate the branch name and state " +
                        "with ____ (4 underscores). Get the branch names from add_tree_node_labels.py. " +
                        "For example, giving Node2____S will change the state at the end of branch Node2 to S")
    parser.add_argument("-o",
                        "--outfile",
                        dest = "outFile",
                        required = True,
                        help = "Output newick tree file")
    args = parser.parse_args()

    #Label the tree
    labelledTree = labelAllClades(Phylo.read(args.tree.name, "newick"))

    #Extract the state changes to a dictionary, node names as keys, states as values
    stateDict = getStateDict(args.state_changes)

    #Label the tree with the given state
    stateTree = labelTreeState(labelledTree, args.root_state, stateDict)

    #Write the state labelled tree
    Phylo.write(stateTree, args.outFile, "newick")