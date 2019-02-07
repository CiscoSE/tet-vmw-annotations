# Tetration-VMWare Annotator

This python script pulls information from vCenter about VM Configuration and state and sends it to Tetration as an annotation.  Currently the following fields can be pushed:

#### Enabled by Default
* **VM Name** *(name)*
* **Host** *(host)*
* **Datastore** *(datastore)*
* **Port Group** *(port_group)*

This script follows the same format as the [ACI Annotator](https://www.github.com/CiscoSE/tet-aci-annotations).  It is a derivative of the "getallvms" sample app for pyvmomi [getallvms.py](https://github.com/vmware/pyvmomi/blob/master/sample/getallvms.py)

# Dependencies
The following required packages can be installed via pip.
```
pip install tetpyclient pyvim pyvmomi argparse
```
# Usage

All of the arguments can be provided via the command line arguments, Environment Variables, or via interactive prompts when launching the script.

```
python annotations.py --help

optional arguments:
  -h, --help            show this help message and exit
  --tet_url TET_URL     Tetration API URL (ex: https://url) - Can
                        alternatively be set via environment variable
                        "ANNOTATE_TET_URL"
  --tet_creds TET_CREDS
                        Tetration API Credentials File (ex:
                        /User/credentials.json) - Can alternatively be set via
                        environment variable "ANNOTATE_TET_CREDS"
  --frequency FREQUENCY
                        Frequency to pull from APIC and upload to Tetration
  --tenant TENANT       Tetration Tenant Name - Can alternatively be set via
                        environment variable "ANNOTATE_TENANT"
  --vc_url VC_URL       vCenter URL (ex: https://url) - Can alternatively be
                        set via environment variable "ANNOTATE_VMW_URL"
  --vc_user VC_USER     vCenter Username - Can alternatively be set via
                        environment variable "ANNOTATE_VMW_USER"
  --vc_pw VC_PW         vCenter Password - Can alternatively be set via
                        environment variable "ANNOTATE_VMW_PW"
```

To change the annotations that are being sent to Tetration, edit the following line at the top of the script.  Order is not important.

```
config['annotations'] = ['port_group','name','host','datastore']
```