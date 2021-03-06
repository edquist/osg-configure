"""
Module to handle attributes related to the slurm jobmanager 
configuration
"""
import os
import logging

from osg_configure.modules import utilities
from osg_configure.modules import configfile
from osg_configure.modules import validation
from osg_configure.modules.jobmanagerconfiguration import JobManagerConfiguration

__all__ = ['SlurmConfiguration']


class SlurmConfiguration(JobManagerConfiguration):
    """Class to handle attributes related to SLURM job manager configuration"""

    # Using PBS emulation in SLURM to interface with globus gatekeeper so
    # config files being used will be the globus PBS config files
    SLURM_CONFIG_FILE = '/etc/grid-services/available/jobmanager-pbs-seg'
    GRAM_CONFIG_FILE = '/etc/globus/globus-pbs.conf'

    def __init__(self, *args, **kwargs):
        # pylint: disable-msg=W0142
        super(SlurmConfiguration, self).__init__(*args, **kwargs)
        self.log('SlurmConfiguration.__init__ started')
        # dictionary to hold information about options
        self.options = {'slurm_location':
                            configfile.Option(name='slurm_location',
                                              default_value='/usr',
                                              mapping='OSG_PBS_LOCATION'),
                        'job_contact':
                            configfile.Option(name='job_contact',
                                              mapping='OSG_JOB_CONTACT'),
                        'util_contact':
                            configfile.Option(name='util_contact',
                                              mapping='OSG_UTIL_CONTACT'),
                        'log_directory':
                            configfile.Option(name='log_directory',
                                              required=configfile.Option.OPTIONAL,
                                              default_value=''),
                        'db_host':
                            configfile.Option(name='db_host',
                                              required=configfile.Option.OPTIONAL,
                                              default_value=''),
                        'db_port':
                            configfile.Option(name='db_port',
                                              required=configfile.Option.OPTIONAL,
                                              opt_type=int,
                                              default_value=3306),
                        'db_user':
                            configfile.Option(name='db_user',
                                              required=configfile.Option.OPTIONAL,
                                              default_value='slurm'),
                        'db_name':
                            configfile.Option(name='db_name',
                                              required=configfile.Option.OPTIONAL,
                                              default_value='slurm_acct_db'),
                        'db_pass':
                            configfile.Option(name='db_pass',
                                              required=configfile.Option.OPTIONAL,
                                              default_value=''),
                        'slurm_cluster':
                            configfile.Option(name='slurm_cluster',
                                              required=configfile.Option.OPTIONAL,
                                              default_value=''),
                        'accept_limited':
                            configfile.Option(name='accept_limited',
                                              required=configfile.Option.OPTIONAL,
                                              opt_type=bool,
                                              default_value=False)}
        self.config_section = "SLURM"
        self.slurm_bin_location = None
        self._set_default = True
        self.log('SlurmConfiguration.__init__ completed')

    def parse_configuration(self, configuration):
        """Try to get configuration information from ConfigParser or SafeConfigParser object given
        by configuration and write recognized settings to attributes dict
        """
        super(SlurmConfiguration, self).parse_configuration(configuration)

        self.log('SlurmConfiguration.parse_configuration started')

        self.check_config(configuration)

        if not configuration.has_section(self.config_section):
            self.log('SLURM section not found in config file')
            self.log('SlurmConfiguration.parse_configuration completed')
            return

        if not self.set_status(configuration):
            self.log('SlurmConfiguration.parse_configuration completed')
            return True

        self.get_options(configuration, ignore_options=['enabled'])

        # set OSG_JOB_MANAGER and OSG_JOB_MANAGER_HOME
        self.options['job_manager'] = configfile.Option(name='job_manager',
                                                        value='SLURM',
                                                        mapping='OSG_JOB_MANAGER')
        self.options['home'] = configfile.Option(name='job_manager_home',
                                                 value=self.options['slurm_location'].value,
                                                 mapping='OSG_JOB_MANAGER_HOME')

        # used to see if we need to enable the default fork manager, if we don't
        # find the managed fork service enabled, set the default manager to fork
        # needed since the managed fork section could be removed after managed fork
        # was enabled
        if (configuration.has_section('Managed Fork') and
                configuration.has_option('Managed Fork', 'enabled') and
                configuration.getboolean('Managed Fork', 'enabled')):
            self._set_default = False

        self.slurm_bin_location = os.path.join(self.options['slurm_location'].value, 'bin')

        self.log('SlurmConfiguration.parse_configuration completed')

    # pylint: disable-msg=W0613
    def check_attributes(self, attributes):
        """Check attributes currently stored and make sure that they are consistent"""
        self.log('SlurmConfiguration.check_attributes started')

        attributes_ok = True

        if not self.enabled:
            self.log('SLURM not enabled, returning True')
            self.log('SlurmConfiguration.check_attributes completed')
            return attributes_ok

        if self.ignored:
            self.log('Ignored, returning True')
            self.log('SlurmConfiguration.check_attributes completed')
            return attributes_ok

        # make sure locations exist
        if not validation.valid_location(self.options['slurm_location'].value):
            attributes_ok = False
            self.log("Non-existent location given: %s" %
                     (self.options['slurm_location'].value),
                     option='slurm_location',
                     section=self.config_section,
                     level=logging.ERROR)

        if not validation.valid_directory(self.slurm_bin_location):
            attributes_ok = False
            self.log("Given slurm_location %r has no bin/ directory" % self.options['slurm_location'].value,
                     option='slurm_location',
                     section=self.config_section,
                     level=logging.ERROR)

        if not validation.valid_contact(self.options['job_contact'].value,
                                        'pbs'):
            attributes_ok = False
            self.log("Invalid job contact: %s" %
                     (self.options['job_contact'].value),
                     option='job_contact',
                     section=self.config_section,
                     level=logging.ERROR)

        if not validation.valid_contact(self.options['util_contact'].value,
                                        'pbs'):
            attributes_ok = False
            self.log("Invalid util contact: %s" %
                     (self.options['util_contact'].value),
                     option='util_contact',
                     section=self.config_section,
                     level=logging.ERROR)

        self.log('SlurmConfiguration.check_attributes completed')
        return attributes_ok

    def configure(self, attributes):
        """Configure installation using attributes"""
        self.log('SlurmConfiguration.configure started')

        if not self.enabled:
            self.log('Slurm not enabled, returning True')
            self.log('SlurmConfiguration.configure completed')
            return True

        if self.ignored:
            self.log("%s configuration ignored" % self.config_section,
                     level=logging.WARNING)
            self.log('SlurmConfiguration.configure completed')
            return True

        if self.gram_gateway_enabled:

            # The accept_limited argument was added for Steve Timm.  We are not adding
            # it to the default config.ini template because we do not think it is
            # useful to a wider audience.
            # See VDT RT ticket 7757 for more information.
            if self.options['accept_limited'].value:
                if not self.enable_accept_limited(SlurmConfiguration.SLURM_CONFIG_FILE):
                    self.log('Error writing to ' + SlurmConfiguration.SLURM_CONFIG_FILE,
                             level=logging.ERROR)
                    self.log('SlurmConfiguration.configure completed')
                    return False
            else:
                if not self.disable_accept_limited(SlurmConfiguration.SLURM_CONFIG_FILE):
                    self.log('Error writing to ' + SlurmConfiguration.SLURM_CONFIG_FILE,
                             level=logging.ERROR)
                    self.log('SlurmConfiguration.configure completed')
                    return False

                    #    self.disable_seg('pbs', SlurmConfiguration.SLURM_CONFIG_FILE)
                    #    if self.options['seg_enabled'].value:
                    #      self.enable_seg('pbs', SlurmConfiguration.SLURM_CONFIG_FILE)
                    #    else:
                    #      self.disable_seg('pbs', SlurmConfiguration.SLURM_CONFIG_FILE)

            # make sure the SEG is disabled
            self.disable_seg('pbs', SlurmConfiguration.SLURM_CONFIG_FILE)
            if not self.setup_gram_config():
                self.log('Error writing to ' + SlurmConfiguration.GRAM_CONFIG_FILE,
                         level=logging.ERROR)
                return False

            if self._set_default:
                self.log('Configuring gatekeeper to use regular fork service')
                self.set_default_jobmanager('fork')

        if self.htcondor_gateway_enabled:
            self.write_binpaths_to_blah_config('slurm', self.slurm_bin_location)
            self.write_blah_disable_wn_proxy_renewal_to_blah_config()
            self.write_htcondor_ce_sentinel()

        self.log('SlurmConfiguration.configure completed')
        return True

    def module_name(self):
        """Return a string with the name of the module"""
        return "SLURM"

    def separately_configurable(self):
        """Return a boolean that indicates whether this module can be configured separately"""
        return True

    def setup_gram_config(self):
        """
        Populate the gram config file with correct values

        Returns True if successful, False otherwise
        """
        contents = open(SlurmConfiguration.GRAM_CONFIG_FILE).read()
        for binfile in ['qsub', 'qstat', 'qdel']:
            bin_location = os.path.join(self.slurm_bin_location, binfile)
            if validation.valid_file(bin_location):
                contents = utilities.add_or_replace_setting(contents, binfile, bin_location)

        if not utilities.atomic_write(SlurmConfiguration.GRAM_CONFIG_FILE, contents):
            return False

        return True

    def enabled_services(self):
        """Return a list of  system services needed for module to work
        """

        if not self.enabled or self.ignored:
            return set()

        return set(['globus-gridftp-server']).union(self.gateway_services())

    def get_db_host(self):
        """
        Return the hostname of the machine with the Slurm DB
        """

        return self.options['db_host'].value

    def get_db_port(self):
        """
        Return the port for Slurm DB service
        """

        return self.options['db_port'].value

    def get_db_user(self):
        """
        Return the user to use when accessing Slurm DB
        """

        return self.options['db_user'].value

    def get_db_pass(self):
        """
        Return the location of the file containing the password
        to use when accessing Slurm DB
        """

        return self.options['db_pass'].value

    def get_db_name(self):
        """
        Return the name of the data slurm is using for accounting info
        """

        return self.options['db_name'].value

    def get_slurm_cluster(self):
        """
        Return the name of the data slurm is using for accounting info
        """

        return self.options['slurm_cluster'].value

    def get_location(self):
        """
        Return the location where slurm is installed
        """

        return self.options['slurm_location'].value
