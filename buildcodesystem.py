"""
Gets JSON representation of codesystems from the HL7 uk website and 
uses them to build codesystem objects from some jinja templates.
This script is called from the BuildValueSets script.
"""
import requests
import jinja2
import os.path
import json

output_dir = "../../src/CodeSystems"
template_dir = "./templates/nodejs"

templateLoader = jinja2.FileSystemLoader(searchpath=template_dir)
templateEnv = jinja2.Environment(loader=templateLoader, trim_blocks=True, lstrip_blocks=True)
template = templateEnv.get_template("CareConnectCodesystem.jinja")
test_template = templateEnv.get_template("CareConnectCodesystemTest.jinja")

def make_class_name(name):
  return name.replace("-","")

def fixup_url(url):
  if url.startswith("http://hl7.org"):
    url_parts = url.split("/")
    url_parts[-1] = "codesystem-%s.json" % (url_parts[-1])
    return "/".join(url_parts)
  else:
    return url

def build_code_system(url,name=None):
  if name==None:
    name = url.split("/")[-1]
  url = fixup_url(url)
  print("Fetching codesystem %s" % (url))
  class_name = make_class_name(name)
  file_name = "%s/%s" % (output_dir, "%s.js" % (class_name))
  test_file_name = "%s/%s" % (output_dir, "/tests/%s.test.js" % (class_name))
  if not url.startswith("http://hl7.org"):
    headers = {"accept":"application/json+fhir"}
  else:
    headers = {}
  req = requests.get(url,headers=headers)
  try:
    if not req.status_code==200:
      raise RuntimeError("Got http status %s While building codesytem" % req.status_code)
    jsn = req.json()
    valid_code = jsn["concept"][0]["code"]
    valid_display = jsn["concept"][0].get("display",None)
    node_code = template.render(js_object=jsn, classname=class_name, url=url)
    node_code = node_code.replace("{","{ ")
    node_code = node_code.replace("}", " }")
    f = open(os.path.join(file_name),"w")
    f.write(node_code)
    f.close()
    test_code = test_template.render(classname=class_name, filename=file_name,valid_code=valid_code,valid_display=valid_display)
    f = open(os.path.join(test_file_name), "w")
    f.write(test_code)
    f.close()
    return class_name, file_name, valid_code, valid_display
  except json.decoder.JSONDecodeError:
    print("Failed to get JSON for CodeSystem")
    return None,None,None,None
  except RuntimeError as ex:
    print(ex)
    return None, None, None, None

def test():
  ret = build_code_system("https://fhir.hl7.org.uk/STU3/CodeSystem/CareConnect-AdmissionMethod-1")
  print(ret)

if __name__=="__main__":
  test()
