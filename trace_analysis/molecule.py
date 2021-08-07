import numpy as np #scientific computing with Python
import matplotlib.pyplot as plt #Provides a MATLAB-like plotting framework
from trace_analysis.analysis.autoThreshold import stepfinder
# from trace_analysis.plugin_manager import PluginManager
# from trace_analysis.plugin_manager import PluginMetaClass
from trace_analysis.plugin_manager import plugins
from trace_analysis.trace_extraction import make_gaussian_mask

@plugins
class Molecule:
    def __init__(self, file):
        self.file = file
        self.index = None
        self._coordinates = None
        self.intensity = None
        self._background=None

        self.isSelected = False

        self.steps = None  #Defined in other classes as: pd.DataFrame(columns=['frame', 'trace', 'state', 'method','thres'])
        self.kon_boolean = None  # 3x3 matrix that is indicates whether the kon will be calculated from the beginning, in-between molecules or for the end only
        #self.bg_scale=np.sum(make_gaussian_mask(self.file.experiment.configuration['find_coordinates']['coordinate_optimization']['coordinates_after_gaussian_fit']['gaussian_width']))

    @property
    def coordinates(self):
        return self._coordinates
    
    @property
    def background(self):
        return self._background
    
    @coordinates.setter
    def coordinates(self, coordinates):
        self._coordinates = np.atleast_2d(coordinates)

    def background(self, background):
        self.background=background # should be dependent on emission channel as well
        
    @property  # this is just for the stepfinder to be called through Molecule. Maybe not needed
    def find_steps(self):
        return stepfinder

    def I(self, emission, Ioff=0):
        return self.intensity[emission, :] - Ioff # - self.background[emission] * self.bg_scale #this number comes from sum(make_gaussian_mask) in trace_extraction

    def E(self, Imin=0, Iroff=0, Igoff=0, alpha=0):
        red = np.copy(self.I(1, Ioff=Iroff))
        green = self.I(0, Ioff=Igoff)
        np.putmask(green, green < 0, 0) # green < 0 is taken as 0
        np.putmask(red, red < Imin, 0)  # the mask makes all elements of acceptor that are below the Imin zero, for E caclulation
        E =  (red - alpha*green) / (green + red - alpha*green)
        E = np.nan_to_num(E)  # correct for divide with zero = None values
        return E

    def plot(self, ylim=(0, 500), xlim=(), Ioff=[],  save=False, **fretkwargs):
        plt.style.use('seaborn-dark')
        plt.style.use('seaborn-colorblind')
        figure = plt.figure(f'{self.file.name}_mol_{self.index}', figsize=(7,4))
        if len(self.file.experiment.pairs) > 0:
            axis_I = figure.add_subplot(211)
        else:
            axis_I = figure.gca()

        axis_I.set_ylabel('Intensity (a.u.)')
        axis_I.set_ylim(ylim[0], ylim[1])
        if xlim == ():
            axis_I.set_xlim(0, self.file.time.max()+1)
        else:
            axis_I.set_xlim(xlim[0], xlim[1])

        axis_I.set_title(f'Molecule {self.index} /{len(self.file.molecules)}')
        if Ioff == []:
            Ioff = [0]*self.file.number_of_channels
        for i, channel in enumerate(self.file.experiment.channels):
            axis_I.plot(self.file.time, self.I(i, Ioff=Ioff[i]), channel)

        if len(self.file.experiment.pairs) > 0:
            axis_E = figure.add_subplot(212, sharex=axis_I)
            axis_E.set_xlabel('Time (s)')
            axis_E.set_ylabel('FRET')
            axis_E.set_ylim(0,1.1)
            for i, pair in enumerate(self.file.experiment.pairs):
                axis_E.plot(self.file.time, self.E(**fretkwargs), 'b')

        plt.tight_layout()
        if save:
            plt.savefig(f'{self.file.relativeFilePath}_mol_{self.index}.eps', transparent=True)
            plt.savefig(f'{self.file.relativeFilePath}_mol_{self.index}.png', facecolor='white', dpi=300, transparent=True)


