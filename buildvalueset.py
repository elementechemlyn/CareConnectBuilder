"""
Gets valuesets and their corresponding codesystems as JSON from the HL7 UK
website. Uses that json in a Jinja template to make a set of classes that
are subclasses of an existing level 1 library i.e. The template extends an
existing ValueSet and CodeSystem object.
Not as bad as the code the build Extensions and Profiles but still a bit
of a mess.
Stores what it build in a Python Pickle file so the classes can be referenced
when building profile and extension classes.
"""
import requests
import jinja2
import os.path
import re
import buildcodesystem
import pickle

output_dir = "../../src/ValueSets"
template_dir = "./templates/nodejs"

templateLoader = jinja2.FileSystemLoader(searchpath=template_dir)
templateEnv = jinja2.Environment(loader=templateLoader, trim_blocks=True, lstrip_blocks=True)
template = templateEnv.get_template("CareConnectValueset.jinja")
test_template = templateEnv.get_template("CareConnectValuesetTest.jinja")

def make_class_name(name):
  return name.replace("-","")

def build_value_set(url,name=None):
  if name==None:
    name = url.split("/")[-1]
  print("Fetching valueset %s" % (url))
  class_name = make_class_name(name)
  file_name = "%s/%s" % (output_dir, "%s.js" % (class_name))
  test_file_name = "%s/%s" % (output_dir, "tests/%s.test.js" % (class_name))
  headers = {"accept": "application/json+fhir"}
  req = requests.get(url,headers=headers)
  jsn = req.json()
  code_system_includes = []
  needs_snomed = False
  if jsn.get("compose",None):
    if jsn["compose"].get("include",None):
      for codesystem in jsn["compose"]["include"]:
        code_system_url = codesystem["system"]
        if code_system_url.find("snomed.info")>=0:
          print("Not retrieving snomed code set %s" % (code_system_url,))
          needs_snomed = True
          example_code = 'snomed'
          example_display = 'snomed'
        else:
          print("Building code system %s" % (code_system_url,))
          code_class_name, code_file_name, example_code, example_display = buildcodesystem.build_code_system(code_system_url)
          if code_class_name:
            code_system_includes.append(
                (code_class_name, code_file_name, code_system_url))
          else: #Failed to build
            return None, None, None, None
  try:
    #Grab a code from the last include set so it matches the last code system built in the loop above.
    valid_code = jsn["compose"]["include"][-1]["concept"][0]["code"]
    valid_display = jsn["compose"]["include"][-1]["concept"][0].get("display", None)
  except KeyError:
    # The ValueSet doesn't have concept codes of it's own. Use a valid_code and display from the last CodeSystem instead.
    valid_code = example_code
    valid_display = example_display
  node_code = template.render(js_object=jsn, classname=class_name, url=url,
                              code_system_includes=code_system_includes, needs_snomed=needs_snomed)
  node_code = node_code.replace("{", "{ ")
  node_code = node_code.replace("}", " }")
  f = open(os.path.join(file_name), "w")
  f.write(node_code)
  f.close()
  test_code = test_template.render(
      classname=class_name, filename=file_name, valid_code=valid_code, valid_display=valid_display, 
      system=code_system_url, needs_snomed=needs_snomed)
  f = open(os.path.join(test_file_name), "w")
  f.write(test_code)
  f.close()
  return class_name, file_name, example_code, example_display

def get_stu3_valuesets():
  # Doing this from the html view for now (can I search the FHIR server for specific versions?)
  valuesetLinks = {}
  headers = {"accept": "text/html"}
  url = "https://fhir.hl7.org.uk/ValueSet"
  req = requests.get(url, headers=headers)
  html = req.text
  links = re.findall("<a href=\"(STU3/ValueSet/.*?)\">", html)
  for link in links:
    url = "https://fhir.hl7.org.uk/%s" % (link,)
    ret = build_value_set(url)
    valuesetLinks[url] = ret
  return valuesetLinks

def test():
  ret = build_value_set(
      "https://fhir.hl7.org.uk/STU3/ValueSet/CareConnect-NHSNumberVerificationStatus-1")
  print(ret)

def build():
  refs = get_stu3_valuesets()
  f = open("ValueSetReferences.pkl","wb")
  pickle.dump(refs,f)
  f.close()

if __name__=="__main__":
  build()
  #test()
