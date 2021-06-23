import os
import numpy as np
from matplotlib import pyplot as plt
from sys import platform

if platform == "darwin":
    from matplotlib import use

    use('WXAgg')
import wx  # cross-platform GUI API
from trace_analysis import Experiment
from trace_analysis import InteractivePlot
from trace_analysis.image_adapt.autoconfig import autoconfig_AND_perform_mapping, autoconfig


# Define path to data, replace by your own directory
def get_path():
    app = wx.App(None)
    dlg = wx.DirDialog(None, message="Choose a folder")
    if dlg.ShowModal() == wx.ID_OK:
        path = dlg.GetPath()
    else:
        path = None
    dlg.Destroy()
    return path


# mainPath = r'D:\pathToDataFolder'
mainPath = get_path()
print('\nExperiments: \n' + mainPath)

# Initialize an experiment
exp = Experiment(mainPath)

# Print files in experiment
for fii in range(len(exp.files)):
    print(f"{fii:3d}.  {exp.files[fii].relativeFilePath}")

# Perform mapping
make_new_mapping = False
if make_new_mapping:
    mapping_file_index = int(input('\nEnter file number for mapping... '))
    mapping_file = exp.files[mapping_file_index]

    # autoconfig_AND_perform_mapping(mapping_file_index, mainPath)

    mapping_file.perform_mapping()
    fig_hdl_map = plt.figure(101)
    mapping_file.show_image(figure=fig_hdl_map)
    mapping_file.mapping.show_mapping_transformation(figure=fig_hdl_map)
    plt.show(block=False)
    plt.pause(0.1)
else:
    mapping_file_index = 0
    mapping_file = exp.files[mapping_file_index]
    print(f"\nMap file loaded from {exp.files[mapping_file_index].relativeFilePath}")

mapping_file.use_mapping_for_all_files()

# Run for all files
file_of_interest = [8, 9, 10]

for fii in file_of_interest:
    print(f'\nWorking on {exp.files[fii].relativeFilePath}')
    exp.files[fii].find_coordinates()
    exp.files[fii].extract_traces()

# Show interactive plot
file_index = 3
molecules = exp.files[0].molecules
int_plot = InteractivePlot(molecules)
int_plot.plot_initialize()
int_plot.plot_molecule()
