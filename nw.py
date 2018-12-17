#!/usr/bin/env python3
# @Author: Marcus
# @Date:   2018-12-16T10:07:12+00:00
# @Project: HMHouse
# @Last modified by:   Marcus
# @Last modified time: 2018-12-17T01:40:30+00:00

# Network Witness
# Connects to switches and compares command output against known good baselines

# TODO: Proper exceptions / ignoring changes
# TODO: Seperate hosts into different lists depending on what we want to do with them?
#   e.g. switches
#        uptime monitoring
#
# TODO: Ping devices?
# TODO: Make baseline only baseline hosts that do not already have a baseline
# TODO: Support for SSH?

# Import stuff
import logging
import pexpect
import os, time, sys
from argparse import ArgumentParser

# ArgumentParser
parser = ArgumentParser(description='Network Witness monitors network devices for changes from baselines', add_help=False)
parser.add_argument('-b','--baseline', help='Creates a baselines from hosts.txt and quits', action='store_true')
parser.add_argument('--debug', help='Enables debugging info', action='store_true')
parser.add_argument('-h', '-?', '--help', help='Help', action='store_true')
args = parser.parse_args()

## logging
# Create the logger
logger = logging.getLogger()

# Set the level
logger.setLevel(logging.DEBUG)

# File logging
fh = logging.FileHandler('nwitness.log')
fh.setLevel(logging.WARN) # Log as low as WARN to file
# Create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s.')
fh.setFormatter(formatter)
logger.addHandler(fh)

# Console logging
ch = logging.StreamHandler()
ch.setLevel(logging.ERROR) # Log as low as ERRORS to console
formatter = logging.Formatter('\033[1;31;40m%(levelname)s - %(message)s. \033[1;37;40m')
ch.setFormatter(formatter)
logger.addHandler(ch)

# Console Log Level: 	ERROR
# Text Log Level: 	    WARN

# General info:         INFO
# Failed Connections:	ERROR
# Config Changes:		WARN (So we can write our own errors in the console, and still record them
# Exceptions:			CRITICAL

def connectTelnet(host, username, password, friendlyName):
# Opens a new connection to the switch

    logging.debug("Entered connectTelnet for " + host)

    # Format the host properly if we're using a non standard port, so telnet can connect
    # e.g. 10.0.0.1:200 becomes 10.0.0.1 200
    host = host.replace(':', ' ')

    try:
        telconn = pexpect.spawn('telnet ' + host, encoding='utf-8')

        time.sleep(1)

        # Check if there is a username
        if username:
            logger.info("User for " + host + " is " + username)
            telconn.expect("Username: ")
            telconn.send(username + "\r")

        # Check if there is a password
        if password:
            logger.info("Password in use for " + host)
            telconn.expect("Password: ")
            telconn.send(password + "\r")

        # Check we have a prompt
        try:
            telconn.expect(['>', '#'], searchwindowsize=-1) # Because GNS3 sometimes spits out crap to begin with
            logger.debug("Successfully got a prompt for " + host)
        except:
            # If we don't have a prompt, check if its asking us to hit RETURN (GNS3), hit return and check again
            logger.debug("Possibly a problem connecting with " + host + " -- retrying. The connection timeout will have caused a noticable delay to the user.")
            telconn.expect("RETURN", searchwindowsize=-1)
            telconn.send("\r")
            try:
                # Check if we have a prompt yet. Or error out of this connection.
                telconn.expect(['>', '#'])
            except:
                logger.error("Unable to gain a prompt on " + host)
                logger.error("The remote prompt may not be using > or #")
                return False

        # Set zero terminal length so --more-- doesn't become a problem
        telconn.send("terminal length 0" + "\r")
        telconn.expect(['>', '#'])

        # Return the connection
        logger.debug("Success! Returning telconn for " + host)
        return telconn

    except Exception as e:
        host = host.replace(' ', ':')
        logger.error("Could not connect to " + friendlyName + " ("+ host + ")")
        logger.debug(e)
        print("\a")
        return False

def getSwitchConfig(host, username, password, friendlyName):
# Returns the switch configuration

    logging.debug("Entered getSwitchConfig for " + host)

    # Open a connection
    telconn = connectTelnet(host, username, password, friendlyName)

    # Check we can connect to that host
    if telconn == False:
        return False

    # Grab interface details
    telconn.send("show ip interface brief | include FastEthernet" + "\r")

    # Close the connection
    telconn.expect(['>', '#'])
    telconn.send("\r")
    telconn.close()

    # Grab the last output
    baselineOutput = telconn.before
    return baselineOutput

def createSwitchBaseline(host, username, password):
# Creates and outputs a baseline for the switch. This function is called by launching NW with --brief

    logging.debug("Entered createSwitchBaseline for " + host)

    # Our output is
    baselineOutput = getSwitchConfig(host, username, password)
    logger.info("Creating baseline for host " + host)

    if baselineOutput == False:
        logger.error("Creating baseline for host " + friendlyName + " ("+ host + ")" + " failed")
        return False

    # Format the host properly if we're using a non standard port, so that it can be written nicely into files
    # e.g. 10.0.0.1:200 becomes 10.0.0.1__200
    host = host.replace(':', '__')

    # Write the last output to a file
    fBaseline = open('known_good_' + host + '.txt', 'w')
    fBaseline.write(baselineOutput)
    fBaseline.close()
    logger.info("Created baseline for host " + host)

    return True

def checkSwitchConfig(host, username, password, friendlyName):
# Checks if the current config matches the running config. Prints lines that do not match.

    logging.debug("Entered checkSwitchConfig for " + host)

    # Grabs the running switch config from getSwitchConfig
    # Puts it into the currentSwitchConfig variable
    currentSwitchConfig = getSwitchConfig(host, username, password, friendlyName)

    # Check the switch config was correctly fetched
    if currentSwitchConfig == False:
        # If we got here it means the config returned as FALSE.
        # This probably means the connection was not successful.
        logging.debug("Current switch config returned as false. The connection likely did not complete? Host: " + host)
        return False

    # Format the host properly if we're using a non standard port, so that it can be written nicely into files
    # e.g. 10.0.0.1:200 becomes 10.0.0.1__200
    host = host.replace(':', '__')

    # Get the configs
    currentSwitchConfig = currentSwitchConfig.splitlines()
    try:
        knownGoodConfig = open('known_good_' + host + '.txt').read().splitlines()
    except Exception as e:
        logger.critical("Could not open known good config for " + host)
        logger.debug(e)
        sys.exit(1)

    if currentSwitchConfig != knownGoodConfig:
        logger.debug("Current config does not match known for " + host)
        for currentCfgLine, goodCfgLine in zip(currentSwitchConfig, knownGoodConfig):
            if currentCfgLine != goodCfgLine:

                # TODO: Do some proper exceptions / ignoring features at some point
                # This is hacky
                # For now, just ignore "FastEthernet0/2 " because it's tamzins tv (note the space)
                if "FastEthernet0/2 " not in currentCfgLine:

                    print("\a")
                    print("\n\033[1;37;41mNetwork Witness Alert!" + "\033[1;37;40m")
                    print("\033[1;37;41m"+ time.strftime('%b %d, %Y at %H:%M%p %Z') + " - " + friendlyName + " ("+ host.replace('__',':') + ")" + " has changed state from known good." + "\033[1;37;40m")
                    print("\033[1;32;40m     Known Good: ", goodCfgLine)
                    print("\033[1;31;40m     Current:    ", currentCfgLine, "\n" + "\033[1;37;40m")
                    logger.warn("CONFIG FILE CHANGE for " + host + ". " + goodCfgLine + " has changed to " + currentCfgLine)
                else:
                    logger.debug("Ignoring " + currentCfgLine + " for host "+ host + " due to exception.")
    else:
        logger.debug("Current config matches known for " + host)

def main():

    print("\033[1;37;40mNetwork Witness. \033[0;37;40mHow about a nice game of chess?")

    ## LOGGING - Enable logging if --debug is set
    if args.debug is True:
        ch.setLevel(logging.DEBUG)
        logging.debug("\033[1;32;40mDebugging enabled\033[0;37;40m")

    ## ARGS HELP OUTPUT
    if args.help is True:
        print("\033[1;37;40mNetwork Witness monitors network devices for changes from baselines\033[0;37;40m\n")
        print("\033[1;37;40mCreate baselines with ./nw --baseline\033[0;37;40m")
        print("Populate hosts_baseline.txt in the format of HOST:PORT,USER,PASS,FRIENDLYNAME \nThis format is required even if there is no username or password")
        print("         EXAMPLE:    10.0.0.1:23,ADMIN,PASSWORD123,SWITCH")
        print("         EXAMPLE:    10.0.0.2:23,,PASSWORD,")
        print("         EXAMPLE:    10.0.0.3:23,,,DSWITCH")
        print("         EXAMPLE:    10.0.0.3:23,,,,\n")
        print("After baselines have generated, rename hosts_baseline.txt to hosts.txt and run the tool normally.")
        sys.exit(1)

    ## BASELINE CREATION
    # Create a baseline with the --baseline argument
    if args.baseline is True:
        logger.debug("Baseline is found to be true. Creating baselines")
        print("Generating baseline(s)")
        try:
            with open('hosts_baseline.txt', 'r') as hostsFile:
                for host in hostsFile:
                    host = host.rstrip("\r\n")
                    host, username, password, friendlyName = host.split(',') # TODO: Make this work without having to put four colons for no user/pw
                    createSwitchBaseline(host, username, password)
                logger.debug("Baselines created")
                print("Baseline Created")
                sys.exit(1)

        # Hosts file does not exist, quitting
        except IOError:
             logger.error("No hosts.txt/baseline file found or incorrectly populated. Please populate/create according to help. Quitting")
             logger.debug("IO Error exception for open(hosts_baseline.txt)")
             sys.exit(1)

        except KeyboardInterrupt:
            print("\033[0;37;40mBye")
            logging.debug("Keyboard Interrupt")
            sys.exit(1)

        # All other exceptions
        except Exception as e:
            print("\033[1;31;40mError: something went wrong creating the baseline :(\n")
            logger.critical(e)
            sys.exit(1)

    ## MONITORING HOSTS
    # Monitor hosts continuously, every 15 seconds
    while True:
        try:
            with open('hosts.txt', 'r') as hostsFile:
                for host in hostsFile:
                        host = host.rstrip("\r\n")
                        host, username, password, friendlyName = host.split(',')
                        logging.debug("Connecting to " + host + " " +friendlyName + " with checkSwitchConfig()")
                        # TODO: Multithreading?
                        checkSwitchConfig(host, username, password, friendlyName)
                        logging.debug("Finished call to " + host + " " +friendlyName + " with checkSwitchConfig(). Moving to next host / Starting Over")

        # A required file does not exist, quitting
        except IOError:
            logger.error("No hosts.txt/baseline file found or incorrectly populated. Please populate/create according to help. Quitting")
            sys.exit(1)

        except KeyboardInterrupt:
            print("\033[0;37;40mBye")
            logging.debug("Keyboard Interrupt")
            sys.exit(1)

        # All other exceptions
        except Exception as e:
            print("\033[1;31;40mError: something went wrong :(\n")
            logger.critical(e)
            break
        # Sleep for 15 seconds after querying all hosts
        try:
            logger.debug("All hosts complete. Sleeping")
            time.sleep(15)
        except KeyboardInterrupt:
            print("\033[0;37;40mBye")
            logging.debug("Keyboard Interrupt")
            sys.exit(1)

if __name__ == "__main__":
    main()