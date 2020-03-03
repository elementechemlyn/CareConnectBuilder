import configparser
import os.path
import os
import shutil

import buildcodesystem
import buildvalueset
import buildextensions
import buildprofiles

config = configparser.ConfigParser()
config.read('config.ini')

output_dir = config["dir"]["output_dir"]
template_dir = config["dir"]["template_dir"]
#CodeSystems and ValueSets have the same names. They must go in a different folder.
#TODO Make these sub-folders configurable?
#TODO Make the download function configurable
codesystem_output = os.path.join(output_dir, 'CodeSystems')
os.makedirs(codesystem_output, exist_ok=True)
os.makedirs(os.path.join(codesystem_output,"tests"), exist_ok=True)
valueset_output = os.path.join(output_dir, 'ValueSets')
os.makedirs(valueset_output, exist_ok=True)
os.makedirs(os.path.join(valueset_output, "tests"), exist_ok=True)
extension_output = os.path.join(output_dir, 'Extensions')
os.makedirs(extension_output, exist_ok=True)
os.makedirs(os.path.join(extension_output, "tests"), exist_ok=True)
profile_output = os.path.join(output_dir, 'Profiles')
os.makedirs(profile_output, exist_ok=True)
os.makedirs(os.path.join(profile_output, "tests"), exist_ok=True)

buildcodesystem.output_dir = codesystem_output
buildcodesystem.template_dir = template_dir
buildvalueset.output_dir = valueset_output
buildvalueset.template_dir = template_dir
buildextensions.output_dir = extension_output
buildextensions.template_dir = template_dir
buildprofiles.output_dir = profile_output
buildprofiles.template_dir = template_dir

buildvalueset.build()
buildextensions.build()
buildprofiles.build()

#Copy the base classes over to the output folder.
base_class_dir = os.path.join(template_dir,'BaseClasses')
base_class_output_dir = os.path.join(output_dir,'BaseClasses')
os.makedirs(base_class_output_dir, exist_ok=True)
for name in os.listdir(base_class_dir):
  full_src_name = os.path.join(base_class_dir,name)
  full_target_name = os.path.join(base_class_output_dir,name) 
  print("Copying %s to %s" % (full_src_name,full_target_name))
  shutil.copyfile(full_src_name,full_target_name)
