"""
This script transforms a set of Profile definitions via Jinja templates into 
code (Javascript at the moment).
It is designed to work on Differentials and use the templates to subclass an
existing level 1 FHIR library.
It's a bit of a mess but it works.
TODO. 
Tidy this up and consolidate it with the same mess used to build Extensions
Broadly:
  1- build_profiles loops through links to profile definitions on the hl7 uk website.
  2- build_profile takes the differential from the structure definition and
    creates a ProfileDef object from it
  3- The ProfileDef object walks the child nodes in the structure def into a 
    slightly logical and propably tree like structure.
  4- The ProfileDef object has a bunch of properties defined that are used in the 
   Jinja template.
"""
import models.structuredefinition
import requests
import jinja2
import os.path
import re
import pickle
import sys
import traceback
import json

ExtensionLinks = None

output_dir = "../../src/Profiles"
template_dir = "./templates/nodejs"

templateLoader = jinja2.FileSystemLoader(searchpath=template_dir)
templateEnv = jinja2.Environment(
    loader=templateLoader, trim_blocks=True, lstrip_blocks=True)
template = templateEnv.get_template("CareConnectConstraint2.jinja")
# test_template = templateEnv.get_template("CareConnectConstraintTest.jinja")

# Used to throw a valueerror if it's a type not yet built into the template
supported_types = []

class ProfileDef(object):
  def __init__(self,name,elements,children):
    self.name = name
    self.elements = elements
    self.children = []
    for c in children.items():
      self.children.append(ProfileDef(c[0],c[1][0],c[1][1]))

  def __str__(self):
    return self.name

  @property
  def extensions(self):
    for c in self.children:
      if c.name=="extension":
        return c
    return None

  @property
  def nonExtensionElements(self): #Returns anything that isn't an extension
    elements = []
    for c in self.children:
      if not c.name=="extension":
        elements.append(c)
    return elements

  @property
  def slices(self):
    s = []
    for c in self.elements:
      if c.sliceName:
        s.append(c)
    return s

  @property
  def discriminator(self):
    #print('Getting discriminator')
    d = []
    for e in self.elements:
       if e.slicingDiscriminator:
         if not e.slicingDiscriminator[0].type == "value":
            raise RuntimeError("Only value discriminators supported")
         d.append(e.slicingDiscriminator)
    if len(d)>1:
      raise RuntimeError("Multiple disriminators found")
    if len(d)>0:
      return d[0][0]
    else:
      return None

  #@property 
  def discriminatorFixedValueFunc(self,sliceName):
    #print("Getting dsc for", sliceName)
    fixed_value = None
    #discriminator_path = self.discriminator.path.split('.')
    if self.discriminator == None:
       raise RuntimeError("Slices without descrimiator not supported")

    discriminator_path = self.discriminator.path.split('.') 
    #print("Desc Path", discriminator_path)
    children = self.children
    path_index = 0
    while(path_index < len(discriminator_path)):
      for c in children:
        #print("looking for", discriminator_path[path_index])
        #print("Got", c.name)
        if c.name == discriminator_path[path_index]:
          if (path_index+1 < len(discriminator_path)):
            #print("Got first level")
            #path_index = path_index+1
            children = c.children
            break
          else:
            for e in c.elements:
              #print(e.element_def.id)
              attrs = dir(e.element_def)
              for a in attrs:
                if a.startswith("fixed") and e.element_def.__dict__[a] and (sliceName in e.element_def.id):
                  #print("fixed value", e.element_def.__dict__[a])
                  if not fixed_value == None:
                    raise RuntimeError("Multiple fixed values found")
                  fixed_value = e.element_def.__dict__[a]
      path_index = path_index+1

    if fixed_value:
      return fixed_value
    else:
      raise RuntimeError("No fixed value found")

  @property
  def discriminatorFixedValue(self):
    #print("Getting dsc for", sliceName)
    fixed_value = None
    discriminator_path = self.discriminator.path
    for c in self.children:
      if c.name == discriminator_path:
        for e in c.elements:
          #print(e.element_def.id)
          attrs = dir(e.element_def)
          for a in attrs:
            if a.startswith("fixed") and e.element_def.__dict__[a]:
              if not fixed_value == None:
                raise RuntimeError("Multiple fixed values found")
              fixed_value = e.element_def.__dict__[a]
    if fixed_value:
      return fixed_value
    else:
      raise RuntimeError("No fixed value found")

class ElementDef(object):
  def __init__(self,element_def):
    self.element_def = element_def

  @property 
  def slicingDiscriminator(self):
    if self.element_def.slicing:
      return self.element_def.slicing.discriminator
    else:
      return None

  @property
  def extensionClass(self):
    try:
      return ExtensionLinks[self.profile][0]
    except KeyError:
      print("Need to build %s. Fall back to base Extension" %  self.profile)
      return "%s%s" % (self.sliceName[0].upper(), self.sliceName[1:])

  @property
  def extensionPath(self):
    try:
      return ExtensionLinks[self.profile][1]
    except KeyError:
      print("Need to build %s  Fall back to base Extension" % self.profile)

  @property
  def profile(self):
    return self.element_def.type[0].profile

  @property
  def max(self):
    return self.element_def.max

  @property
  def min(self):
    return self.element_def.min

  @property
  def name(self):
    return re.split("[.:]",self.element_def.id)[-1]

  @property
  def sliceName(self):
    s = self.element_def.sliceName
    if(s):
      parts = re.sub(r"([A-Z])", r" \1", s.replace("-", " ")).split()
      newParts = parts[0:1]
      newParts.extend(["%s%s" % (x[0].upper(),x[1:]) for x in parts[1:]])
      return "".join(newParts)

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

def get_children_of(differential,parent=None):
  if parent == None:
    parent =  get_elements_at_level(differential,0)
    if len(parent)>1:
      raise ValueError("Multiple parent types not supported")
    parent_defs = get_elements_at_path(differential,parent[0])
    return {parent[0] : (parent_defs,get_children_of(differential,parent[0]))}
  else:
    elements = {}
    for e in differential.element:
      parts = re.match("^%s\.([^.]+).*$" % parent, e.path)
      if parts:
        if not parts.group(1) in elements:
          element_defs = get_elements_at_path(differential,"%s.%s" % (parent,parts.group(1)))
          elements[parts.group(1)] = (element_defs,get_children_of(differential,"%s.%s" % (parent,parts.group(1))))
    return elements

def get_elements_at_path(differential,path):
  elements = []
  for e in differential.element:
    parts = re.match("^%s$" % path, e.path)
    if parts:
      elements.append(ElementDef(e))
  return elements
  
def get_elements_at_level(differential,level=0):
  elements = []
  for e in differential.element:
    parts = e.path.split(".")
    if len(parts)>level:
      elements.append(parts[level])
  return list(set(elements))

def make_class_name(name):
  return name.replace("-", "")

def build_profile(url, name=None, extensions_done=None, headers={"accept": "application/json+fhir"}):
  print("Building profile from %s" % (url))
  if name == None:
    name = url.split("/")[-1]

  class_name = make_class_name(name)
  file_name = "%s/%s" % (output_dir, "%s.js" % (class_name))
  test_file_name = "%s/%s" % (output_dir, "%s.test.js" % (class_name))
  
  req = requests.get(url, headers=headers)
  jsn = req.json()
  structureDef = models.structuredefinition.StructureDefinition(jsn, strict=False)
  if (structureDef.differential == None):
    raise ValueError("Only diffs supported")
  if (not structureDef.derivation == "constraint"):
    raise ValueError("Only resource contraints supported")

  profile_def = get_children_of(structureDef.differential)
  #return profile_def
  main_name = list(profile_def.keys())[0]
  profile =  ProfileDef(main_name,profile_def[main_name][0],profile_def[main_name][1])
  #return profile
  node_code = template.render(structure=structureDef, profile=profile)
  f = open(os.path.join(file_name), "w")
  f.write(node_code)
  f.close()
  structureDef.classname = structureDef.name.replace("-", "")
  return True, structureDef, file_name

def build():
  global ExtensionLinks
  # Doing this from the html view for now (can I search the FHIR server for specific versions?)
  f = open("ExtensionReferences.pkl", "rb")
  ExtensionLinks = pickle.load(f)
  f.close()
  profiles_done = []
  profiles_todo = []
  headers = {"accept": "text/html"}
  url = "https://fhir.hl7.org.uk/StructureDefinition"
  req = requests.get(url, headers=headers)
  html = req.text
  # print(html)
  links = re.findall("<a href=\"(STU3/StructureDefinition/.*?)\">", html)
  for link in links:
    print(link)
    url = "https://fhir.hl7.org.uk/%s" % (link,)
    try:
      built,profile_def,filename = build_profile(url,extensions_done=profiles_done)
      if(built):
        profiles_done.append((url,profile_def.classname,filename))
      else:
        profiles_todo.append(url)
    except:
      print(sys.exc_info(), file=sys.stderr)
      traceback.print_tb(sys.exc_info()[2])
  return profiles_done

def test():
  return build_profile('https://fhir.hl7.org.uk/STU3/StructureDefinition/CareConnect-Organization-1')
  #build_profile('https://fhir.hl7.org.uk/STU3/StructureDefinition/CareConnect-Location-1')
  #build_profile('https://fhir.hl7.org.uk/STU3/StructureDefinition/CareConnect-Encounter-1')
  #build_profile('https://fhir.hl7.org.uk/STU3/StructureDefinition/CareConnect-Patient-1')
  #return build_profile('https://fhir.hl7.org.uk/STU3/StructureDefinition/CareConnect-Composition-1')

if __name__=="__main__":
  #build()
  test()
