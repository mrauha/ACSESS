#!/usr/bin/env python
#-*- coding: utf-8 -*-
import os, sys
sys.path.append('.')
sys.path.append('./Filters/')
from rdkit import Chem
from rdkit import RDLogger
from rdkithelpers import *
import mprms
import importlib
import random


######################################################
# Read run parameters from mprms.py,
# and store them all in StoredParams.py
######################################################
def Initialize():

    # define which type of module attributes are allowed to be changed
    primitiveTypes = (str, float, bool, int, list, tuple, type(None))
    isinputfunction= lambda var: hasattr(var, '__name__') and var.__name__ in [
            'fitnessfunction', 'extender']
    normalvar =  lambda var: type(var) in primitiveTypes or isinputfunction(var)
    notbuiltin = lambda var: not var.startswith('_')

    def goodvar(var, mod):
        return notbuiltin(var) and normalvar(getattr(mod, var))

    # set&log random seed
    if hasattr(mprms, 'rseed'):
        random.seed(mprms.rseed)
    else:
        mprms.rseed = random.randint(1, 1000)
        random.seed(mprms.rseed)
    print "random seed:", mprms.rseed

    # Set RDKit verbosity
    if hasattr(mprms, 'verbose') and not mprms.verbose:
        lg = RDLogger.logger()
        lg.setLevel(RDLogger.CRITICAL)
        print "RDKit logging level -> CRITICAL"
    else:
        setattr(mprms, 'verbose', True)

    # force mprms to have some properties
    if not hasattr(mprms, 'optimize'):
        mprms.optimize = False
    if not hasattr(mprms, 'restart'):
        mprms.restart = False
    if not hasattr(mprms, 'cellDiversity'):
        mprms.cellDiversity = False

    # Decide which modules have to be imported:
    # The following modules will always be loaded:
    _modules = [
        'acsess',
        'mutate',
        'filters',
        'Filters.DefaultFilters',
        'Filters.ExtraFilters',
        'Filters.GDBFilters',
        'drivers',
        'rdkithelpers',
        'output',
    ]

    # Here we decide wich other modules to load as well:
    # set diversity framework: distance or similarity based.
    if hasattr(mprms, 'metric') and not mprms.metric in ['', 'similarity']:
        setattr(mprms, '_similarity', False)
        _modules.append('distance')
        _modules.append('molproperty')
    else:
        setattr(mprms, '_similarity', True)
        _modules.append('similarity')

    # set diversity algorithm: Maximin or CellDiversity
    if hasattr(mprms, 'cellDiversity') and mprms.cellDiversity is True:
        _modules.append('celldiversity')

    # set optimization algorithm. pure diversity or property-optimizing
    if mprms.optimize:
        _modules.append('objective')

    # check if the CINDES program will be used to calculate the property values
    if hasattr(mprms, 'CINDES_interface') and mprms.CINDES_interface is True:
        _modules.append('QCindes')

    # Import the modules / Set the global variables / Initiate modules
    for module in _modules:
        # module names are relative so add a dot
        rmodule = '{}'.format(module)
        # and import them relative the our ACSESS package:
        _Mod = importlib.import_module(rmodule, package='ACSESS')
        # get normal global variables of the modules
        modvars = [var for var in dir(_Mod) if goodvar(var, _Mod)]
        for modvar in modvars:
            # check if mprms has same attr:
            if hasattr(mprms, modvar):
                attrvalue = getattr(mprms, modvar)
                #than change it:
                setattr(_Mod, modvar, attrvalue)
                if len(repr(attrvalue))>41:
                    print "set attr: {:_>22}.{:20}".format(module, modvar)
                else:
                    print "set attr: {:_>22}.{:_<19} : {}".format(module, modvar, attrvalue)

        # initialize module if it has an Init function
        if hasattr(_Mod, 'Init') and callable(getattr(_Mod, 'Init')):
            getattr(_Mod, 'Init')()

    return


######################################################
# Get starting library and pool
#
#  Library comes from, in order of precedence:
#      1. Restart files ('itX.lib.gz') (for restarts only)
#      2. Read from mprms.seedfile
#      3. Read from mprms.seedlib
#      4. Preset in previous options are not met
#         (benzene + cyclohexane)
#
#  Pool comes from:
#      1. Restart file ('pool.lib.gz') (for restarts only)
#      2. Read from mprms.poolfile
#      3. Read from mprms.poollib
#      4. Copy of library
######################################################
def StartLibAndPool(restart):
    startiter = 0

    if hasattr(mprms, 'nSeed'):
        nSeed = mprms.nSeed
    else:
        nSeed = -1

    #####################
    #   Start library   #
    #####################

    #case 1: restart file ('itX.lib.gz')
    if restart:
        for i in reversed(xrange(mprms.nGen + 1)):
            filename = "it{}.smi".format(i)
            if os.path.isfile(filename):
                startiter = i + 1
                break
        else:
            raise SystemExit('RESTART but no iteration files found')
        supplier = Chem.SmilesMolSupplier(filename, sanitize=False)
        lib = [mol for mol in supplier]
        print 'RESTARTING calculation from iteration', startiter - 1,
        print 'with {} molecules'.format(len(lib))
    #case 2: read from mprms.seedfile
    elif hasattr(mprms, 'seedFile'):
        seedFile = mprms.seedFile
        supplier = Chem.SmilesMolSupplier(seedFile, sanitize=False)

        lib = [mol for mol in supplier]
        print "Seeding with " + str(len(lib)) + " molecules from " + seedFile

    #case 3: read from mprms.seedlib
    elif hasattr(mprms, 'seedLib'):
        lib = mprms.seedLib
        if nSeed > 0:
            lib = lib[:nSeed]
        lib = [Chem.MolFromSmiles(mol, sanitize=False) for mol in lib]
        print "read seedLib with {:d} molecules from input".format(len(lib))
        if len(lib) == 0:
            raise ValueError, "Seedlib is empty."

    #case 4: predefined as (benzene + cyclohexane)
    else:
        print 'Seeding library with presets'
        lib = []
        lib.append(Chem.MolFromSmiles('C1CCCCC1', sanitize=False))
        lib.append(Chem.MolFromSmiles('C1=CC=CC=C1', sanitize=False))

    #####################
    #     Start pool    #
    #####################

    if restart:
        # there has to be a poolfile.
        if not hasattr(mprms, 'poolFile'):
            setattr(mprms, 'poolFile', 'pool.smi')

    #case 1: read from mprms.poolfile
    if hasattr(mprms, 'poolFile'):
        pool = [mol for mol in lib]
        supplier = Chem.SmilesMolSupplier(mprms.poolFile, sanitize=False)
        newpool = [mol for mol in supplier]
        pool += newpool
        print 'Initializing pool from ' + mprms.poolFile + ' of ' +\
                   str(len(newpool)) + ' molecules'

    #case 2: read from mprms.poollib
    elif hasattr(mprms, 'poolLib'):
        #poolLib is a list of SMILES
        pool = mprms.poolLib
        pool = [Chem.MolFromSmiles(mol, False) for mol in lib]
        pool = pool + lib
        if len(pool) == 0:
            raise ValueError, "Poollib is empty."
        print "Initializing pool from mprms.poolLib"

    #case 3: copy from library
    else:
        print 'Initializing pool from library'
        pool = [mol for mol in lib]

    # set isosmi
    setisosmi = lambda mol: mol.SetProp('isosmi', Chem.MolToSmiles(mol, True))
    map(setisosmi, pool)
    map(setisosmi, lib)

    ######### sanitize lib & pool
    ll1, lp1 = (len(lib), len(pool))
    lib = filter(Sane, lib)
    pool = filter(Sane, pool)
    ll2, lp2 = (len(lib), len(pool))
    if not ll1 == ll2:
        print "removed {:d} unsane molecules from lib  | libsize : {:d}".format(
            ll1 - ll2, ll2)
    if not lp1 == lp2:
        print "removed {:d} unsane molecules from pool | poolsize: {:d}".format(
            lp1 - lp2, lp2)
    ######### Do we have to refilter restarted pool/lib ?
    if restart:
        refilter=True
        if refilter:
            import drivers
            dostartfilter = startiter>=drivers.startFilter
            dogenstrucs   = startiter>=drivers.startGenStruc
            lib = drivers.DriveFilters(lib, dostartfilter, dogenstrucs)
            pool = drivers.DriveFilters(pool, dostartfilter, dogenstrucs)

    if len(lib)>mprms.subsetSize + mprms.edgeLen:
        raise NotImplementedError('len startinglibrary larger than maxSubsetSize')

    return startiter, lib, pool
