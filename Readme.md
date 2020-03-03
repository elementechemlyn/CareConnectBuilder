# CareConnect FHIR Builder

__**Work In Progress**__

Python scripts to download CareConnect FHIR profiles from the HL7 uk website and 
process them into code using a set of Jinja templates.

This project differs from existing FHIR code generation tools in that it is designed to
work on the differential of a level 2 structure definition and subclass existing FHIR classes.

In theory it could also be run on a level 3 differential to subclass level 2 classes generated by this project - let me know how you get on :-)

Templates are included to produce nodeJS classes that are subclasses of the classes from 
the https://github.com/Asymmetrik/node-fhir-server-core project.

## Building the classes ##
Copy config.ini.sample to config.ini and adjust to point to your chosen output directory.

If you wish to use a different set of templates - adjust the template_dir too.

If you wish to change the Base Classes add your own to the BaseClasses directory under the templates directory
Then ...
```
pip install -r requirements.txt
python buildall.py
```
## Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details of the process for submitting pull requests to us.

## Credits
Python fhir models used in this project are from the SMART Health IT Python client

https://github.com/smart-on-fhir/client-py


## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.

JSON representations of resources used in and by this project are Copyright © HL7.org 2011+

HL7® and FHIR® are the registered trademarks of Health Level Seven International

