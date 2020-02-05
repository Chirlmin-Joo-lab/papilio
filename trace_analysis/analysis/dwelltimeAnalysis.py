# -*- coding: utf-8 -*-
"""
Created on Mon Oct 28 11:32:58 2019

@author: ikatechis
"""

import os
import numpy as np
import sys
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import SAfitting
sns.set(style="ticks")
sns.set_color_codes()


def analyze(dwells_data, dist, configuration):
    conf = configuration
    d = apply_config_to_data(dwells_data, dist, conf)
    figures = []
    fit_data = []
    keys_with_data = []
    for key in d.keys():
        if d[key].empty:  # check if the dataframe is empty
            print(f'{dist} dataFrame for {key} is empty')
            continue
        dwells = d[key].loc[:,dist].values
        if conf['FitBool']:
            fit_res = fit(dwells, model=conf['model'], Nfits=config['Nfits'],
                           include_over_Tmax=config['TmaxBool'],
                           bootstrap=config['BootBool'],
                           boot_repeats=config['BootRepeats'])
            fit_data.append(fit_res)
        print(f'plotting {key} {dist}')
        figure = plot(dwells, dist, trace=key, binsize=conf['binsize'],
                      scale=conf['scale'], style=conf['PlotType'],
                      fit_data=fit_data)
        figures.append(figure)
        keys_with_data.append(key)

    if fit_data != []:
        fit_data = pd.concat(fit_data, axis=1, keys=keys_with_data)
    return d, figures, fit_data

def fit(dwells, model='1Exp', Nfits=1,  include_over_Tmax=True,
        bootstrap=True, boot_repeats=100):
    if model == '1Exp+2Exp':
        fit_result = []
    #     for model in ['1Exp', '2Exp']:
    #         result = fit_function(dwells, model, Nfits,  include_over_Tmax,
    #                               bootstrap, boot_repeats)
    #         fit_result.append(result)
    #     fit_result = pd.concat(fit_result, axis=1, ignore_index=True)
    #     return fit_result

    # fit_result = fit_function(dwells, model, Nfits,  include_over_Tmax,
    #                               bootstrap, boot_repeats)

    # return fit_result



def plot(dwells, dist='offtime', trace='red', binsize='auto', scale='log',
         style='dots', color='from_trace', fit_data=None):

    try:
        bsize = float(binsize)
        bin_edges = np.arange(min(dwells), max(dwells) + bsize, bsize)
    except ValueError:
        if binsize == 'Auto':
            binsize = 'auto'
        bin_edges = binsize
    values, bins = np.histogram(dwells, bins=bin_edges, density=True)
    centers = (bins[1:] + bins[:-1]) / 2.0
    fig = plt.figure(f'Histogram {trace} {dist}s', figsize=(4,3), dpi=200)

    if color == 'from_trace':
        if dist == 'offtime':
            color = 'r'*(trace=='red') + 'g'*(trace=='green') + \
                    'b'*(trace=='FRET') + 'sandybrown'*(trace=='total')
        if dist == 'ontime':
            color = 'firebrick'*(trace=='red') + 'olive'*(trace=='green') + \
                    'darkviolet'*(trace=='FRET') + 'saddlebrown'*(trace=='total')
    label = f'{dist} pdf, N={dwells.size}'
    if style == 'dots':

        plt.plot(centers, values, 'o', color=color, label=label)
    if style == 'bars':
        plt.bar(centers, values, color=color, label=label,
                width=(bins[1] - bins[0]))
    if style == 'line':
        plt.plot(centers, values, '-', lw=2, color=color, label=label)

    if scale in ['Log', 'Log-Log']:
        plt.yscale('log')

    if scale == 'Log-Log':
        plt.xscale('log')

    plt.legend()
    plt.ylabel('Probability')
    plt.xlabel(f'{dist} (s)')
    plt.locator_params(axis='y', nbins=3)
    plt.tight_layout()
    plt.show()
    return fig


def apply_config_to_data(dwells_data, dist, config):
    d = dwells_data
    # Select the requested sides
    side_list = ['l'*bool(config['side']['left']),
               'm'*bool(config['side']['middle']),
               'r'*bool(config['side']['right'])]

    if dist == 'offtime':
        d = d[d.side.isin(side_list)]
    if dist == 'ontime':
        d = d[d.onside.isin(side_list)]
    # apply min, max conditions
    if config['max'] in ['Max', 'max']:
        d = d[d[dist] > float(config['min'])]
    else:
        d = d[d[dist] > float(config['min']) & d[dist] < float(config['max'])]

    data = {}

    for key in config['trace'].keys():
        if config['trace'][key]:
            data[key] = d[d['trace'] == key]
        else:
            pass

    return data


def get_average_dwell(dwells):
    #  correct for dwell exceeding the measurement time minus 5 sec
    Tmax = dwells.max() - 5
    Ntot = dwells.size
    Ncut = dwells[dwells > Tmax].size
    avrg_dwell = np.average(dwells[dwells < Tmax])
    avrg_dwell = avrg_dwell + Ncut*Tmax/Ntot
    return avrg_dwell

if __name__ == '__main__':
    filename = 'F:/Google Drive/PhD/Programming - Data Analysis/traceanalysis/traces/'
    filename += 'hel0_dwells_data.xlsx'

    data = pd.read_excel(filename, index_col=[0, 1], dtype={'kon' :np.str})
    print(data.shape)
    config = {'trace': {'red': True, 'green': False, 'total': False, 'FRET': False},
         'side': {'left': True, 'middle': True, 'right': True},
         'min': '0', 'max': 'Max',
         'scale': 'Normal',
         'PlotType': 'dots',
         'binsize': 'auto',
         'FitBool': False,
         'TmaxBool': False,
         'BootBool': False,
         'model': '1Exp',
         'Nfits': '10',
         'BootRepeats': '100'}

    result = analyze(data, 'offtime', config)
