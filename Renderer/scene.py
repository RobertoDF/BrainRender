import sys
sys.path.append('./')   # <- necessary to import packages from other directories within the project

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from collections import namedtuple
from vtkplotter import *

from Utils.data_io import load_json
from Utils.data_manipulation import *
from colors import *
from variables import *
from Renderer.ABA_analyzer import ABA
from Utils.mouselight_parser import render_neurons
from settings import *

"""
    The code below aims to create a scene to which actors can be added or removed, changed etc..
    It also facilitates the interaction with the scene (e.g. moving the camera) and the creation of 
    snapshots or animated videos. 
    The class Scene is based on the Plotter class of Vtkplotter: https://github.com/marcomusy/vtkplotter/blob/master/vtkplotter/plotter.py
    and other classes within the same package. 
"""

class Scene(ABA):  # subclass brain render to have acces to structure trees
    VIP_regions = DEFAULT_VIP_REGIONS
    VIP_color = DEFAULT_VIP_COLOR

    def __init__(self, brain_regions=None, regions_aba_color=False, 
                    neurons=None, tracts=None, add_root=None, verbose=True):
        """[Creates and manages a Plotter instance]
        
        Keyword Arguments:
            brain_regions {[list]} -- [list of brain regions acronyms or ID numebers to be added to the sceme] (default: {None})
            regions_aba_color {[bool]} -- [If true use the Allen Brain Atlas regions coors] (default: {False})
            
            neurons {[str]} -- [path to JSON file for neurons to be rendered by mouselight_parser. Alternatively it can 
                                    be a list of already rendered neurons' actors] (default: {None})
            tracts {[list]} -- [list of tractography items, one per experiment] (default: {None})
            add_root {[bool]} -- [if true add semi transparent brain shape to scene. If None the default setting is used] (default: {None})

        """
        ABA.__init__(self)
        self.verbose = verbose
        self.regions_aba_color = regions_aba_color

        if add_root is None:
            add_root = DISPLAY_ROOT

        self.plotter = Plotter(axes=4, size="full")
        self.actors = {"regions":{}, "tracts":[], "neurons":[], "root":None, "injection_sites":[], "others":[]}

        if brain_regions is not None:
            self.add_brain_regions(brain_regions)

        if neurons is not None:
            self.add_neurons(neurons)

        if tracts is not None:
            self.add_tractography(tracts)

        if add_root:
            self.add_root()
        else:
            self.root = None

        self.rotated = False  # the first time the scene is rendered it must be rotated, the following times it must not be rotated
        self.inset = None  # the first time the scene is rendered create and store the inset here

    ####### UTILS
    def check_obj_file(self, structure, obj_file):
        # checks if the obj file has been downloaded already, if not it takes care of downloading it
        if not os.path.isfile(obj_file):
                        mesh = self.space.download_structure_mesh(structure_id = structure[0]["id"], 
                                                        ccf_version ="annotation/ccf_2017", 
                                                        file_name=obj_file)

    @staticmethod
    def check_region(region):
        if not isinstance(region, int) and not isinstance(region, str):
            raise ValueError("region must be a list, integer or string")
        else: return True

    def get_region_color(self, regions):
        if not isinstance(regions, list):
            return self.structure_tree.get_structures_by_acronym([regions])[0]['rgb_triplet']
        else:
            return [self.structure_tree.get_structures_by_acronym([r])[0]['rgb_triplet'] for r in regions]

    ###### ADD ACTORS TO SCENE

    def add_root(self, render=True):
        structure = self.structure_tree.get_structures_by_acronym(["root"])[0]
        obj_path = os.path.join(models_fld, "root.obj")
        self.check_obj_file(structure, obj_path)
        self.root = self.plotter.load(obj_path, c=ROOT_COLOR, alpha=ROOT_ALPHA)
        self.root.pickable(value=False)

        if render:
            self.actors['root'] = self.root

    def add_brain_regions(self, brain_regions, VIP_regions=None, VIP_color=None, colors=None, use_original_color=False): 
        if VIP_regions is None:
            VIP_regions = self.VIP_regions
        if VIP_color is None:
            VIP_color = self.VIP_color

        # check that we have a list
        if not isinstance(brain_regions, list):
            self.check_region(brain_regions)
            brain_regions = [brain_regions]
    
        # check the colors input is correct
        if colors is not None:
            if isinstance(colors[0], list):
                if not len(colors) == len(brain_regions): raise ValueError("when passing colors as a list, the number of colors must match the number of brain regions")
                for col in colors:
                    if not check_colors(col): raise ValueError("Invalide colors in input: {}".format(col))
            else:
                if not check_colors(colors): raise ValueError("Invalide colors in input: {}".format(colors))
                colors = [colors for i in range(len(brain_regions))]

        # loop over all brain regions
        for i, region in enumerate(brain_regions):
            self.check_region(region)

            # if it's an ID get the acronym
            if isinstance(region, int):
                region = self.structure_tree.get_region_by_id([region])[0]['acronym']

            if self.verbose: print("Rendering: ({})".format(region))
            
            # get the structure and check if we need to download the object file
            structure = self.structure_tree.get_structures_by_acronym([region])[0]
            obj_file = os.path.join(models_fld, "{}.obj".format(structure["acronym"]))
            self.check_obj_file(structure, obj_file)

            # check which color to assign to the brain region
            if self.regions_aba_color or use_original_color:
                color = [x/255 for x in structure["rgb_triplet"]]
            else:
                if region in VIP_regions:
                    color = VIP_color
                else:
                    if colors is None:
                        color = DEFAULT_STRUCTURE_COLOR
                    elif isinstance(colors, list):
                        color = colors[i]
                    else: color = colors

            if region in VIP_regions:
                alpha = 1
            else:
                alpha = DEFAULT_STRUCTURE_ALPHA

            # Load the object file as a mesh and store the actor
            self.actors["regions"][region] = self.plotter.load(obj_file, c=color, 
                                                                        alpha=alpha) 

    def add_neurons(self, neurons, **kwargs):
        if isinstance(neurons, str):
            if os.path.isfile(neurons):
                self.actors["neurons"].extend(render_neurons(neurons, **kwargs))
            else:
                raise FileNotFoundError("The neurons JSON file provided cannot be found: {}".format(neurons))
        elif isinstance(neurons, list):
            self.actors["neurons"].extend(neurons)
        else:
            raise ValueError("the 'neurons' variable passed is neither a filepath nor a list of actors: {}".format(neurons))

    def add_tractography(self, tractography, color=None, display_injection_structure=False, display_onlyVIP_injection_structure=False, color_by="manual", 
                        VIP_regions=[], VIP_color="red", others_color="white"):
        """
            Color can be either None (in which case default is used), a single color (e.g. "red") or 
            a list of colors, in which case each tractography tract will have the corresponding color

            display_injection_structure: display the brain region in which the injection was made
            display_onlyVIP_injection_structure: if True and display_injection_structure == True then only the brian structures that are in VIP_regions are displayed
            color_by: [str] specify how to color tracts and, if displayed, injection structures.
                    options are:
                        - manual: use the value of 'color'
                        - region: color by the ABA RGB color of injection region
                        - target_region: color tracts and regions in VIP_regions with VIP_coor and others with others_color
        """
        # check argument
        if not isinstance(tractography, list):
            if isinstance(tractography, dict):
                tractography = [tractography]
            else:
                raise ValueError("the 'tractography' variable passed must be a list of dictionaries")
        else:
            if not isinstance(tractography[0], dict):
                raise ValueError("the 'tractography' variable passed must be a list of dictionaries")

        if not isinstance(VIP_regions, list): raise ValueError("VIP_regions should be a list of acronyms")

        # check coloring mode used and prepare a list COLORS to use for coloring stuff
        if color_by == "manual":
            # check color argument
            if color is None:
                color = TRACT_DEFAULT_COLOR
            elif isinstance(color, list):
                if not len(color) == len(tractography):
                    raise ValueError("If a list of colors is passed, it must have the same number of items as the number of tractography traces")
                else:
                    for col in color:
                        if not check_colors(col): raise ValueError("Color variable passed to tractography is invalid: {}".format(col))

                    COLORS = color                
            else:
                if not check_colors(color):
                    raise ValueError("Color variable passed to tractography is invalid: {}".format(color))
                else:
                    COLORS = [color for i in range(len(tractography))]

        elif color_by == "region":
            COLORS = [self.get_region_color(t['structure-abbrev']) for t in tractography]

        elif color_by == "target_region":
            if not check_colors(VIP_color) or not check_colors(others_color): raise ValueError("Invalid VIP or other color passed")
            try:
                COLORS = [VIP_color if t['structure-abbrev'] in VIP_regions else others_color for t in tractography]
            except:
                raise ValueError("Something went wrong while getting colors for tractography")

        # add actors to represent tractography data
        actors = []
        for i, (t, color) in enumerate(zip(tractography, COLORS)):
            # represent injection site as sphere
            actors.append(Sphere(pos=t['injection-coordinates'], c=color, r=INJECTION_VOLUME_SIZE*t['injection-volume'], alpha=TRACTO_ALPHA))

            # show brain structures in which injections happened
            if display_injection_structure:
                if t['structure-abbrev'] not in list(self.actors['regions'].keys()):
                    if display_onlyVIP_injection_structure and t['structure-abbrev'] in VIP_regions:
                        self.add_brain_regions([t['structure-abbrev']], colors=color)

            # get tractography points and represent as list
            points = [p['coord'] for p in t['path']]
            actors.append(shapes.Tube(points, r=TRACTO_RADIUS, c=color, alpha=TRACTO_ALPHA, res=TRACTO_RES))

        self.actors['tracts'].extend(actors)

    def add_injection_sites(self, experiments, color=None):
        """[Creates Spherse at the location of injections with a volume proportional to the injected volume]
        
        Arguments:
            experiments {[list]} -- [list of dictionaries with experiments metadata]
        """
        # check arguments
        if not isinstance(experiments, list):
            raise ValueError("experiments must be a list")
        if not isinstance(experiments[0], dict):
            raise ValueError("experiments should be a list of dictionaries")

        #c= cgeck color
        if color is None:
            color = INJECTION_DEFAULT_COLOR

        injection_sites = []
        for exp in experiments:
            injection_sites.append(Sphere(pos=(exp["injection_x"], exp["injection_y"], exp["injection_z"]),
                    r = INJECTION_VOLUME_SIZE*exp["injection_volume"]*3, 
                    c=color
                    ))

        self.actors['injection_sites'].extend(injection_sites)

    def add_sphere_at_point(self, pos=[0, 0, 0], radius=100, color="black", alpha=1):
        self.actors['others'].append(Sphere(pos=pos, r=radius, c=color, alpha=alpha))

    ####### RENDER SCENE
    def apply_render_style(self):
        actors = self.get_actors()

        for actor in actors:
            actor.lighting(style=SHADER_STYLE)


    def get_actors(self):
        all_actors = []
        for k, actors in self.actors.items():
            if isinstance(actors, dict):
                if len(actors) == 0: continue
                all_actors.extend(list(actors.values()))
            elif isinstance(actors, list):
                if len(actors) == 0: continue
                for act in actors:
                    if isinstance(act, dict):
                        all_actors.extend(flatten_list(list(act.values())))
                    elif isinstance(act, list):
                        all_actors.extend(act)
                    else: 
                        all_actors.append(act)
            else:
                all_actors.append(actors)
        return all_actors

    def render(self, interactive=True):
        self.apply_render_style()

        if not self.rotated:
            roll, azimuth, elevation = 180, -35, -25
            self.rotated = True
        else:
            roll = azimuth = elevation = None

        if DISPLAY_INSET and self.inset is None:
            if self.root is None:
                self.add_root(render=False)

            self.inset = self.root.clone().scale(.5)
            self.inset.alpha(1)
            self.plotter.showInset(self.inset, pos=(0.9,0.2))  

        if VERBOSE:
            print(INTERACTIVE_MSG)
        else:
            print("\n\npress 'q' to Quit")

        if interactive:
            show(self.get_actors(), interactive=True, roll=roll, azimuth=azimuth, elevation=elevation)  
        else:
            show(*self.get_actors(), interactive=False,  offscreen=True, roll=roll, azimuth=azimuth, elevation=elevation)  


    ####### VIDEO & ANIMATION

    # def video_maker(self, dest_path, vp=None, *args, **kwargs):
    #     if vp is None: 
    #         vp = self.plot_structures_3d(*args, render=False, **kwargs)

    #     fld, video = os.path.split(dest_path)
    #     os.chdir(fld)
    #     video = Video(name=video, duration=3)
        
    #     for i  in range(80):
    #         vp.show()  # render the scene first
    #         vp.camera.Azimuth(2)  # rotate by 5 deg at each iteration
    #         # vp.camera.Zoom(i/40)
    #         video.addFrame()
    #     video.close()  # merge all the recorded frames


    ####### EXPORT SCENE
    def export_scene(self, merge_actors=True, filename='scene.vtk'):
        actors = self.get_actors()

        if merge_actors:
            scene = merge(*actors)

        save(scene, os.path.join(rendered_scenes, filename))
        # scene.write(os.path.join(rendered_scenes, filename))
        # exportWindow(actors, os.path.join(rendered_scenes, filename))


if __name__ == "__main__":
    # get vars to populate test scene
    br = ABA()

    tract = br.get_projection_tracts_to_target("PRNr")


    # makes cene
    scene = Scene(tracts=tract)
    scene.add_brain_regions(["PRNr", "PRNc"], VIP_color="red", VIP_regions=["PRNr", "PRNc"])

    afferents = br.analyze_afferents("PRNc")
    scene.add_brain_regions([a for a in afferents.acronym.values[-10:] if a not in ["PRNc", "PRNr"]])

    tract = br.get_projection_tracts_to_target("PRNc")
    scene.add_tractography(tract, color="r")

    afferents = br.analyze_afferents("PRNr")
    scene.add_brain_regions([a for a in afferents.acronym.values[-10:] if a not in ["PRNc", "PRNr"]])
    # scene.add_injection_sites(experiments)


    scene.render()