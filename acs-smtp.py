__author__ = "Taran Ulrich"
__license__ = "GPL"
__version__ = "1.0.0"
__maintainer__ = "Taran Ulrich"
__status__ = "Production"

"""Simple SMTP server that receives emails and forwards them using Azure Communication Services (ACS).
Make sure to install the required packages:
pip install aiosmtpd azure-communication-email
pip install aioconsole

Prerequisites

You need an Azure subscription, a Communication Service Resource, and an Email Communication Resource with an active Domain.

To create these resource, you can use the Azure Portal, the Azure PowerShell, or the .NET management client library.
Azure Portal: https://docs.microsoft.com/azure/communication-services/quickstarts/create-communication-resource?tabs=windows&pivots=platform-azp
Azure PowerShell: https://docs.microsoft.com/powershell/module/az.communication/new-azcommunicationservice
.NET Management Client Library: https://docs.microsoft.com/azure/communication-services/quickstarts/create-communication-resource?tabs=windows&pivots=platform-net

"""

import asyncio
import base64
import email
import aioconsole
import json
import time
from aiosmtpd.controller import Controller
from aiosmtpd.handlers import Message
from email import policy
from azure.communication.email import EmailClient
#from azure.core.exceptions import HttpResponseError

#ACS Documentation
#https://pypi.org/project/azure-communication-email/

#TODO
# Add error handling for ACS email sending
# Add proper logging


#TESTING
# test if display name inside senderAddress works
# determine if it's okay to have empty keys in message
#    - will have an empty html key increase detection?

# Will need to make sure sending profile has same domain as ACS email resource
# - use API to update/create a sending profile in gophish   
# - automatically create sending profile in gophish - https://docs.getgophish.com/api-documentation/sending-profiles#create-sending-profile
# Will need the application to be registered Entra application
#https://learn.microsoft.com/en-us/entra/identity-platform/howto-create-service-principal-portal#register-an-application-with-microsoft-entra-id-and-create-a-service-principal
#

# use PowerAutomate to send emails
# - use API to update/create a PowerAutomate flow that sends an email via ACS
# - this bypasses the need for registering an application in Entra 
#https://learn.microsoft.com/en-us/connectors/acsemail/

class CommunicationServices:
    def __init__(self, accessKey, endpoint):
        # Ensure endpoint is correctly formatted
        if not endpoint.startswith("https://"):
            endpoint = "https://" + endpoint
        if not endpoint.endswith(".communication.azure.com/"):
            endpoint = endpoint + ".communication.azure.com/"
        
        self.connection_string = f"endpoint={endpoint};accessKey={accessKey}"
        # Authenticate to Azure Communication Services
        self.client = EmailClient.from_connection_string(self.connection_string);

    
    def send_email(self, message):
        poller = self.client.begin_send(message)
        result = poller.result()
        return result




class SMTPHandler:
    def __init__(self, AzureEmailClient):
        self.acs = AzureEmailClient

    async def handle_DATA(self, server, session, envelope): 
        """Handle incoming email data, parse it, and forward it using Azure Communication Services."""

        # Parse email content
        msg = email.message_from_bytes(envelope.original_content, policy=policy.default)
        # Construct ACS email message
        message = {
            "content": {},
            "recipients": {
                "to": []
                #"cc": [], #not currently used in gophish
                #"bcc": [] #not currently used in gophish
            },
            "senderAddress": envelope.mail_from 
        }
        #print(f"\n--- New Email Received ---\nWHOLE DAMN THING: \n{msg}")


        #handle body contents
        if msg.is_multipart(): #email has multiple parts (text, html, attachments, etc)
            for part in msg.walk():
                content_type = part.get_content_type()

                if part.is_attachment():
                    #initialize attachments list if it doesn't exist yet
                    if 'attachments' not in message:
                        message['attachments'] = []
                    #add attachment to ACS message
                    message['attachments'].append({
                        "name": part.get_filename(),
                        "attachmentType": content_type,
                        "contentInBase64": part.get_payload()
                    })
                    continue #did all we want with the attachment, skip to next part
                try:
                    body = part.get_body()
                except:
                    print(f"Part ID: {part_id}")
                    print(f"Could not decode text: \n{part}") #log this better
                    raise Exception("DecodeError", "Could not decode email part")
                # add received body to appropriate part of ACS message 
                if body:   
                    if content_type == 'text/plain':
                        message["content"]["plainText"] = body.get_content()
                    
                    elif content_type == 'text/html':
                            message["content"]["html"] = body.get_content()
        else: 
            try:
                body = msg.get_content()
            except:
                #exception should return 500 error to sender and display the raised exception in emails details
                print(f"Could not decode text: \n{part}")
                raise Exception("DecodeError", "Could not decode email")
            content_type = msg.get_content_type() #email is not multi-part, check if it's text or html

            # add received body to appropriate part of ACS message    
            if content_type == 'text/plain':
                    message["content"]["plainText"] = body
            elif content_type == 'text/html':
                    message["content"]["html"] = body
            else: #idk what else could be recieved, but just in case
                raise Exception("UnknownContentType", "The email content type is neither text/plain nor text/html")
        
        #handle recipients
        #gophish only sends to one recipient at a time, so just use the first one
        message["recipients"]["to"].append({"address": envelope.rcpt_tos[0]}) 
        if "<" in msg["To"]:  #extract display name if available
            message["recipients"]["to"][0]["displayName"] = msg["To"].split("<")[0].strip() 
        
        #handle subject
        if msg["Subject"]:
            message["content"]["subject"] = msg["Subject"]
        
        
        #print(json.dumps(message, indent=4))

        # Send email using Azure Communication Service
        self.acs.send_email(message)
        return '250 Message accepted for delivery'

async def main(AzureEmailClient):
    # Create and start the SMTP server
    controller = Controller(SMTPHandler(AzureEmailClient), hostname='localhost', port=1025, decode_data=True)
    print("Starting SMTP server...", end="", flush=True)
    try:
        controller.start()
        print("DONE")
        print(f"SMTP server started on {controller.hostname}:{controller.port}")
        print("Waiting for emails...Enter q to stop")
        # Keep the server running
        while True:
            # wait for user input to quit
            input_char = await aioconsole.ainput()                
            if input_char.lower() == 'q' or input_char.lower() == 'quit' or input_char.lower() == 'exit':
                print("Shutting down server...", end="", flush=True)
                break
            await asyncio.sleep(1)
    except Exception as e:
        print(f"Failed to start SMTP server:\n{e}")
    finally:
        #properly stop the server on user quit
        controller.stop()
        time.sleep(1)
        print("DONE")
        exit()

if __name__ == "__main__":
    with open("config.json") as config_file:
        config = json.load(config_file)
    
    print("Authenticating to Azure Communication Services...", end="", flush=True)
    try: # Authenticate to Azure Communication Services + initialize EmailClient
        AzureEmailClient = CommunicationServices(accessKey=config["key"], endpoint=config["endpoint"])
    except Exception as e:
        print(f"Failed to authenticate to Azure Communication Services: {e}")
        exit(1)
    print("DONE")

    asyncio.run(main(AzureEmailClient))
