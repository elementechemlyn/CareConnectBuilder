"""
This script transforms a set of Extension definitions via Jinja templates into
code (Javascript at the moment).
It is designed to work on Differentials and use the templates to subclass an
existing level 1 FHIR library.
It's a bit of a mess but it works.
TODO. 
Tidy this up and consolidate it with the same mess used to build Profiles
Broadly:
  1- build_extensions loops through links to Extension definitions on the hl7 uk website.
  2- build_extension takes the differential from the structure definition and
    creates an ExtensionDef object from it
  3- The ExtensionDef object has a bunch of properties defined that are used in the 
   Jinja template.
Stores what it builds in a Python pickle file so the classes can be referenced when
building profile objects.
"""
import models.structuredefinition
import requests
import jinja2
import os.path
import re
import buildvalueset
import pickle
import sys
import traceback

valuesetLinks = None

output_dir = "../../src/Extensions"
template_dir = "./templates/nodejs"

templateLoader = jinja2.FileSystemLoader(searchpath=template_dir)
templateEnv = jinja2.Environment(
    loader=templateLoader, trim_blocks=True, lstrip_blocks=True)
template = templateEnv.get_template("CareConnectExtension.jinja")
test_template = templateEnv.get_template("CareConnectExtensionTest.jinja")

# Used to throw a valueerror if it's a type not yet built into the template
supported_types = ['codeableconcept','boolean','datetime','string','reference','code','extension']

"""
A fairly simple object to wrap the list of element definitions
and provide properties that can be used in the Jinja template.
TODO - This is a real mess and probably not very robust.
It currently works for the Care Connect extensions though.
An alternative (and equally messy) method of parsing the elements
and their paths is used in the BuildProfiles script.
"""
class ExtensionDef(object):
  def __init__(self,element_def):
    self.element_def = element_def

  @property
  def max(self):
    return self.element_def.max

  @property
  def min(self):
    return self.element_def.min

  @property
  def is_orphan(self):
    return (self.element_def.path.find(".")>-1)

  @property
  def url(self):
    for c in self.element_def.children:
      if(c.element_def.id and re.match("^.*?\.url$",c.element_def.id)):
        return c.element_def.fixedUri
    return None

  @property
  def sliceNames(self):
    slice_names = []
    for c in self.element_def.children:
      if c.element_def.sliceName:
        slice_names.append(c.element_def.sliceName)
    return slice_names

  @property
  def slices(self):
    slices = []
    for c in self.element_def.children:
      if c.element_def.sliceName:
        slices.append(c)
    return slices

  def getSlice(self,slice_name):
    for c in self.element_def.children:
      if c.element_def.sliceName == slice_name:
        return c
    return None

  @property
  def name(self):
    return re.split("[.:]",self.element_def.id)[-1]

  @property
  def classname(self):
    name = self.url.split("/")[-1]
    return name.replace("-", "")

  @property
  def binding(self):
    if self.value and (self.valueType=="codeableconcept" or self.valueType=="code"):
      return self.value.element_def.binding
    elif self.choice and (("codeableconcept" in self.typeCodeList) or ("code" in self.typeCodeList)):
      return self.choice.element_def.binding
    return None

  @property 
  def valueSetDetail(self):
    binding_url = self.binding.valueSetReference.reference
    # TODO Fix up the url for PrescribedElsewhere
    if binding_url == "https://fhir.nhs.uk/STU3/ValueSet/CareConnect-PrescribedElsewhere-1":
      binding_url = "https://fhir.hl7.org.uk/STU3/ValueSet/CareConnect-PrescribedElsewhere-1"
    return valuesetLinks[binding_url]

  @property
  def valueSetModule(self):
    return self.valueSetDetail[1]

  @property
  def valueSetExampleCode(self):
    return self.valueSetDetail[2]

  @property
  def valueSetExampleDisplay(self):
    return self.valueSetDetail[3]

  @property
  def typeTargetProfileList(self):
    if self.has_value:
      return [self.value.element_def.type.targetProfile]
    elif self.has_choice:
      return [x.targetProfile for x in self.choiceTypes if x.targetProfile is not None]

  @property
  def typeCodeList(self):
    if self.value:
      return [self.valueType.lower()]
    elif self.choice:
      codes = [t.code.lower() for t in self.choiceTypes]
      return list(set(codes)) #Make the list unique
    else:
      return ["extension"]

  @property
  def typeCodeListValueValue(self):
    if self.value:
      return [self.valueValueType]
    elif self.choice:
      codes = ["value%s%s" % (t.code[0].upper(),t.code[1:])for t in self.choiceTypes]
      return list(set(codes))  # Make the list unique

  @property
  def choiceTypes(self):
    if self.choice:
      return self.choice.element_def.type
    return None

  @property
  def valueType(self):
    if self.value:
      return self.value.element_def.type[0].code.lower()
    return None

  @property
  def valueValueType(self):
    if self.value:
      return "value%s%s" % (self.value.element_def.type[0].code[0].upper(), self.value.element_def.type[0].code[1:])
    return None

  @property
  def value(self):
    for c in self.element_def.children:
        if(re.match("^.*?\.value[a-zA-Z:]+$", c.element_def.id if c.element_def.id else c.element_def.path)):
          if(c.element_def.max == None) or (int(c.element_def.max) > 1):
            return c
    return None

  @property
  def has_value(self):
    return not (self.value==None)

  @property
  def choice(self):
    for c in self.element_def.children:
      if(re.match("^.*?\.value\[x\][a-zA-Z:]*$", c.element_def.id if c.element_def.id else c.element_def.path)):
        if(c.element_def.max == None) or (int(c.element_def.max) > 1):
          return c
    return None

  @property
  def has_choice(self):
    return (not self.choice == None)

  @property
  def has_extension(self):
    for c in self.element_def.children:
      if(re.match("^.*?\.extension+$", c.element_def.id if c.element_def.id else c.element_def.path)):
        return True
    return False

def get_element_children(differential,element=None):
  if element==None:
    sorted_elements = sort_elements_by_id(differential.element)
    return get_element_children(differential,sorted_elements[0])
  else:
    if element.id:
      base_id = element.id
    else:
      base_id = element.path
    element.children = []
    for e in differential.element:
      if element and re.match("^%s[.:][^.]+$" % (base_id,), e.id if e.id else e.path):
        element.children.append(get_element_children(differential,e))
    return ExtensionDef(element)

def get_id_depth(element):
  if element.id:
    return len(element.id.split("."))
  else:
    return len(element.path.split("."))

def sort_elements_by_id(elements):
  sorted_elements = sorted(elements,key=get_id_depth)
  return sorted_elements

def make_class_name(name):
  return name.replace("-", "")


def build_extension(url, name=None, extensions_done=None, headers={"accept": "application/json+fhir"}):
  print("Building extension from %s" % (url))
  if name == None:
    name = url.split("/")[-1]

  class_name = make_class_name(name)
  file_name = "%s/%s" % (output_dir, "%s.js" % (class_name))
  test_file_name = "%s/%s" % (output_dir, "tests/%s.test.js" % (class_name))
  
  req = requests.get(url, headers=headers)
  jsn = req.json()
  structureDef = models.structuredefinition.StructureDefinition(jsn)
  if (structureDef.differential == None):
    raise ValueError("Only diffs supported")
  extension_def = get_element_children(structureDef.differential)
  if extension_def.is_orphan: # The diff doesn't have a "parent". Take it from the snapshot and try again.
    structureDef.differential.element.insert(0,structureDef.snapshot.element[0])    
    extension_def = get_element_children(structureDef.differential)

  if (not extension_def.name == "Extension"):
    raise ValueError("%s Not an extension!" % extension_def.name)
    pass

  for t in extension_def.typeCodeList:
    if not t in supported_types:
      raise ValueError("Type %s not yet supported" % (t,))

  if (extension_def.has_value):
    pass
  elif (extension_def.has_choice):
    pass
  elif (extension_def.has_extension):
    slices = extension_def.slices
    for slice in slices:
      if slice.url.startswith("https://fhir.hl7.org.uk/STU3/StructureDefinition/"):
        raise ValueError("Link to existing object. TODO!")
      if slice.has_extension:
        return None,extension_def,None
        raise ValueError("Only value/choice sub extensions supported")
  else:
    return extension_def
    raise ValueError("Don't understand this extension!")
  
  extension_def.scriptname = "BuildExtensions.py"
  extension_def.filename = file_name
  node_code = template.render(extension=extension_def)
  f = open(os.path.join(file_name), "w")
  f.write(node_code)
  f.close()
  test_code = test_template.render(extension=extension_def)
  f = open(os.path.join(test_file_name), "w")
  f.write(test_code)
  f.close()
  return True,extension_def,file_name

def build():
  global valuesetLinks
  
  f = open("ValueSetReferences.pkl", "rb")
  valuesetLinks = pickle.load(f)
  f.close()
  # Doing this from the html view for now (can I search the FHIR server for specific versions?)
  extensions_done = {}
  extensions_todo = {}
  headers = {"accept": "text/html"}
  url = "https://fhir.hl7.org.uk/Extensions"
  req = requests.get(url, headers=headers)
  html = req.text
  links = re.findall("<a href=\"/(STU3/StructureDefinition/.*?)\">", html)
  for link in links:
    url = "https://fhir.hl7.org.uk/%s" % (link,)
    try:
      built,extension_def,filename = build_extension(url,extensions_done=extensions_done)
      if(built):
        extensions_done[url] = (extension_def.classname,filename)
      else:
        extensions_todo[url] = (None,None)
    except:
      print(sys.exc_info(), file=sys.stderr)
      traceback.print_tb(sys.exc_info()[2])
  f = open("ExtensionReferences.pkl", "wb")
  pickle.dump(extensions_done, f)
  f.close()
  return extensions_done

def test():
  #built, extension_def, filename = build_extension('https://fhir.hl7.org.uk/STU3/StructureDefinition/Extension-CareConnect-AdmissionMethod-1')
  #print(b.binding)
  #built, extension_def, filename = build_extension(
  #    'https://fhir.hl7.org.uk/STU3/StructureDefinition/Extension-CareConnect-ActualProblem-1')
  #print(b.typeTargetProfileList)
  #built, extension_def, filename = build_extension('https://fhir.hl7.org.uk/STU3/StructureDefinition/Extension-CareConnect-AllergyIntoleranceEnd-1')
  #print(b.typeCodeList)
  #built, extension_def, filename = build_extension(
  #    'https://fhir.hl7.org.uk/STU3/StructureDefinition/Extension-CareConnect-AnaestheticIssues-1')
  #built, extension_def, filename = build_extension(
  #    'https://fhir.hl7.org.uk/STU3/StructureDefinition/Extension-CareConnect-DataController-1')
  #print(extension_def.typeCodeList)
  built, extension_def, filename = build_extension(
      'https://fhir.hl7.org.uk/STU3/StructureDefinition/Extension-CareConnect-ConditionRelationship-1')
  return built, extension_def, filename

if __name__=="__main__":
  build()
  #test()
