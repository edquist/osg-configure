""" Module to handle attributes related to the sge jobmanager configuration """

import os
import logging
import subprocess

from osg_configure.modules import utilities
from osg_configure.modules import configfile
from osg_configure.modules import validation
from osg_configure.modules.jobmanagerconfiguration import JobManagerConfiguration

__all__ = ['SGEConfiguration']


class SGEConfiguration(JobManagerConfiguration):
    """Class to handle attributes related to sge job manager configuration"""

    SGE_CONFIG_FILE = '/etc/grid-services/available/jobmanager-sge-seg'
    GRAM_CONFIG_FILE = '/etc/globus/globus-sge.conf'
    BLAH_CONFIG = JobManagerConfiguration.BLAH_CONFIG

    def __init__(self, *args, **kwargs):
        # pylint: disable-msg=W0142
        super(SGEConfiguration, self).__init__(*args, **kwargs)
        self.log('SGEConfiguration.__init__ started')
        # option information
        self.options = {'sge_root':
                            configfile.Option(name='sge_root',
                                              mapping='OSG_SGE_ROOT'),
                        'sge_cell':
                            configfile.Option(name='sge_cell',
                                              default_value='default',
                                              mapping='OSG_SGE_CELL'),
                        'sge_config':
                            configfile.Option(name='sge_config',
                                              default_value='/etc/sysconfig/gridengine'),
                        'sge_bin_location':
                            configfile.Option(name='sge_bin_location',
                                              default_value='default'),
                        'job_contact':
                            configfile.Option(name='job_contact',
                                              mapping='OSG_JOB_CONTACT'),
                        'util_contact':
                            configfile.Option(name='util_contact',
                                              mapping='OSG_UTIL_CONTACT'),
                        'seg_enabled':
                            configfile.Option(name='seg_enabled',
                                              required=configfile.Option.OPTIONAL,
                                              opt_type=bool,
                                              default_value=False),
                        'log_file':
                            configfile.Option(name='log_file',
                                              required=configfile.Option.OPTIONAL,
                                              default_value=''),
                        'log_directory':
                            configfile.Option(name='log_directory',
                                              required=configfile.Option.OPTIONAL,
                                              default_value=''),
                        'default_queue':
                            configfile.Option(name='default_queue',
                                              required=configfile.Option.OPTIONAL,
                                              default_value=''),
                        'validate_queues':
                            configfile.Option(name='validate_queues',
                                              required=configfile.Option.OPTIONAL,
                                              opt_type=bool,
                                              default_value=False),
                        'available_queues':
                            configfile.Option(name='available_queues',
                                              required=configfile.Option.OPTIONAL,
                                              default_value=''),
                        'accept_limited':
                            configfile.Option(name='accept_limited',
                                              required=configfile.Option.OPTIONAL,
                                              opt_type=bool,
                                              default_value=False)}
        self._set_default = True
        self.config_section = "SGE"
        self.log('SGEConfiguration.__init__ completed')

    def parse_configuration(self, configuration):
        """Try to get configuration information from ConfigParser or SafeConfigParser object given
        by configuration and write recognized settings to attributes dict
        """
        super(SGEConfiguration, self).parse_configuration(configuration)

        self.log('SGEConfiguration.parse_configuration started')

        self.check_config(configuration)

        if not configuration.has_section(self.config_section):
            self.log('SGE section not found in config file')
            self.log('SGEConfiguration.parse_configuration completed')
            return

        if not self.set_status(configuration):
            self.log('SGEConfiguration.parse_configuration completed')
            return True

        self.get_options(configuration, ignore_options=['enabled'])

        # fill in values for sge_location and home
        self.options['job_manager'] = configfile.Option(name='job_manager',
                                                        value='SGE',
                                                        mapping='OSG_JOB_MANAGER')
        self.options['home'] = configfile.Option(name='job_manager_home',
                                                 value=self.options['sge_root'].value,
                                                 mapping='OSG_JOB_MANAGER_HOME')
        self.options['osg_sge_location'] = configfile.Option(name='sge_location',
                                                             value=self.options['sge_root'].value,
                                                             mapping='OSG_SGE_LOCATION')

        # if log_directory is set and log_file is not, copy log_directory over to
        # log_file and warn the admin
        if (self.options['log_directory'].value != '' and
                    self.options['log_file'].value == ''):
            self.options['log_file'].value = self.options['log_directory'].value
            self.log("log_directory is deprecated, please use log_file instead",
                     option='log_directory',
                     section=self.config_section,
                     level=logging.WARNING)
        # used to see if we need to enable the default fork manager, if we don't
        # find the managed fork service enabled, set the default manager to fork
        # needed since the managed fork section could be removed after managed fork
        # was enabled
        if (configuration.has_section('Managed Fork') and
                configuration.has_option('Managed Fork', 'enabled') and
                configuration.getboolean('Managed Fork', 'enabled')):
            self._set_default = False

        self.log('SGEConfiguration.parse_configuration completed')

    # pylint: disable-msg=W0613
    def check_attributes(self, attributes):
        """Check attributes currently stored and make sure that they are consistent"""
        self.log('SGEConfiguration.check_attributes started')
        attributes_ok = True
        if not self.enabled:
            self.log('SGE not enabled, returning True')
            self.log('SGEConfiguration.check_attributes completed')
            return attributes_ok

        if self.ignored:
            self.log('Ignored, returning True')
            self.log('SGEConfiguration.check_attributes completed')
            return attributes_ok

        # make sure locations exist
        if not validation.valid_location(self.options['sge_root'].value):
            attributes_ok = False
            self.log("Non-existent location given: %s" %
                     (self.options['sge_root'].value),
                     option='sge_root',
                     section=self.config_section,
                     level=logging.ERROR)

        settings_file = os.path.join(self.options['sge_root'].value,
                                     self.options['sge_cell'].value,
                                     'common',
                                     'settings.sh')

        if not validation.valid_file(settings_file):
            attributes_ok = False
            self.log("$SGE_ROOT/$SGE_CELL/common/settings.sh not present: %s" %
                     settings_file,
                     option='sge_cell',
                     section=self.config_section,
                     level=logging.ERROR)

        if not validation.valid_directory(self.options['sge_bin_location'].value):
            attributes_ok = False
            self.log("sge_bin_location not valid: %s" % self.options['sge_bin_location'].value,
                     option='sge_bin_location',
                     section=self.config_section,
                     level=logging.ERROR)

        if not validation.valid_contact(self.options['job_contact'].value,
                                        'sge'):
            attributes_ok = False
            self.log("Invalid job contact: %s" %
                     (self.options['job_contact'].value),
                     option='job_contact',
                     section=self.config_section,
                     level=logging.ERROR)

        if not validation.valid_contact(self.options['util_contact'].value,
                                        'sge'):
            attributes_ok = False
            self.log("Invalid util contact: %s" %
                     (self.options['util_contact'].value),
                     option='util_contact',
                     section=self.config_section,
                     level=logging.ERROR)

        if self.options['seg_enabled'].value:
            if (self.options['log_file'].value is None or
                    not validation.valid_file(self.options['log_file'].value)):
                mesg = "%s is not a valid file path " % self.options['log_file'].value
                mesg += "for sge log files"
                self.log(mesg,
                         section=self.config_section,
                         option='log_file',
                         level=logging.ERROR)
                attributes_ok = False

        key = 'sge_config'
        if (not self.options[key].value or
                not validation.valid_file(self.options[key].value)):
            attributes_ok = False
            self.log("%s is not a valid file: %s" % (key, self.options[key].value),
                     section=self.config_section,
                     option=key,
                     level=logging.ERROR)

        self.log('SGEConfiguration.check_attributes completed')
        return attributes_ok

    def configure(self, attributes):
        """Configure installation using attributes"""
        self.log('SGEConfiguration.configure started')

        if not self.enabled:
            self.log('SGE not enabled, returning True')
            self.log('SGEConfiguration.configure completed')
            return True

        if self.ignored:
            self.log("%s configuration ignored" % self.config_section,
                     level=logging.WARNING)
            self.log('SGEConfiguration.configure completed')
            return True

        if self.gram_gateway_enabled:

            # The accept_limited argument was added for Steve Timm.  We are not adding
            # it to the default config.ini template because we do not think it is
            # useful to a wider audience.
            # See VDT RT ticket 7757 for more information.
            if self.options['accept_limited'].value:
                if not self.enable_accept_limited(SGEConfiguration.SGE_CONFIG_FILE):
                    self.log('Error writing to ' + SGEConfiguration.SGE_CONFIG_FILE,
                             level=logging.ERROR)
                    self.log('SGEConfiguration.configure completed')
                    return False
            else:
                if not self.disable_accept_limited(SGEConfiguration.SGE_CONFIG_FILE):
                    self.log('Error writing to ' + SGEConfiguration.SGE_CONFIG_FILE,
                             level=logging.ERROR)
                    self.log('SGEConfiguration.configure completed')
                    return False

            if self.options['seg_enabled'].value:
                self.enable_seg('sge', SGEConfiguration.SGE_CONFIG_FILE)
            else:
                self.disable_seg('sge', SGEConfiguration.SGE_CONFIG_FILE)

            if not self.setup_gram_config():
                self.log('Error writing to ' + SGEConfiguration.GRAM_CONFIG_FILE,
                         level=logging.ERROR)
                return False

            if self._set_default:
                self.log('Configuring gatekeeper to use regular fork service')
                self.set_default_jobmanager('fork')

        if self.htcondor_gateway_enabled:
            self.setup_blah_config()
            self.write_binpaths_to_blah_config('sge', self.options['sge_bin_location'].value)
            self.write_blah_disable_wn_proxy_renewal_to_blah_config()
            self.write_htcondor_ce_sentinel()

        self.log('SGEConfiguration.configure started')
        return True

    def module_name(self):
        """Return a string with the name of the module"""
        return "SGE"

    def separately_configurable(self):
        """Return a boolean that indicates whether this module can be configured separately"""
        return True

    def setup_gram_config(self):
        """
        Populate the gram config file with correct values

        Returns True if successful, False otherwise
        """
        buf = open(SGEConfiguration.GRAM_CONFIG_FILE).read()

        for binfile in ['qsub', 'qstat', 'qdel', 'qconf']:
            bin_location = os.path.join(self.options['sge_bin_location'].value, binfile)
            if validation.valid_file(bin_location):
                buf = utilities.add_or_replace_setting(buf, binfile, bin_location)

        for setting in ['sge_cell', 'sge_root', 'sge_config']:
            buf = utilities.add_or_replace_setting(buf, setting, self.options[setting].value)

        if self.options['seg_enabled'].value:
            buf = utilities.add_or_replace_setting(buf, 'log_path', self.options['log_file'].value)

        if self.options['default_queue'].value != '':
            buf = utilities.add_or_replace_setting(buf, 'default_queue', self.options['default_queue'].value)

            if self.options['validate_queues'].value:
                buf = utilities.add_or_replace_setting(buf, 'validate_queues', 'yes', quote_value=False)
            else:
                buf = utilities.add_or_replace_setting(buf, 'validate_queues', 'no', quote_value=False)

        if self.options['available_queues'].value != '':
            buf = utilities.add_or_replace_setting(buf, 'available_queues', self.options['available_queues'].value)

        if not utilities.atomic_write(SGEConfiguration.GRAM_CONFIG_FILE, buf):
            return False
        return True

    def setup_blah_config(self):
        """
        Populate blah.config with correct values

        Return True if successful, False otherwise
        """
        if os.path.exists(self.BLAH_CONFIG):
            contents = utilities.read_file(self.BLAH_CONFIG)
            contents = utilities.add_or_replace_setting(contents, "sge_rootpath", self.options['sge_root'].value,
                                                        quote_value=True)
            contents = utilities.add_or_replace_setting(contents, "sge_cellname", self.options['sge_cell'].value,
                                                        quote_value=True)
            return utilities.atomic_write(self.BLAH_CONFIG, contents)
        return False

    def enabled_services(self):
        """Return a list of  system services needed for module to work
        """
        if not self.enabled or self.ignored:
            return set()

        services = set(['globus-gridftp-server'])
        services.update(self.gateway_services())
        if self.options['seg_enabled'].value:
            services.add('globus-scheduler-event-generator')
            services.add('globus-gatekeeper')
        return services

    def get_accounting_file(self):
        """
        Return the location of the SGE Accounting file
        """

        return os.path.join(self.options['sge_root'].value,
                            self.options['sge_cell'].value,
                            'common',
                            'accounting')
