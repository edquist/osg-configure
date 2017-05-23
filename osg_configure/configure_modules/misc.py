""" Module to handle attributes and configuration for misc. sevices """

import re
import logging
import os
import shutil

from osg_configure.modules import exceptions
from osg_configure.modules import utilities
from osg_configure.modules import configfile
from osg_configure.modules import validation
from osg_configure.modules import gums_supported_vos
from osg_configure.modules.baseconfiguration import BaseConfiguration

__all__ = ['MiscConfiguration']

GSI_AUTHZ_LOCATION = "/etc/grid-security/gsi-authz.conf"
GUMS_CLIENT_LOCATION = "/etc/gums/gums-client.properties"
LCMAPS_DB_LOCATION = "/etc/lcmaps.db"
LCMAPS_DB_TEMPLATES_LOCATION = "/usr/share/lcmaps/templates"
HTCONDOR_CE_CONFIG_FILE = '/etc/condor-ce/config.d/50-osg-configure.conf'

VALID_AUTH_METHODS = ['gridmap', 'local-gridmap', 'xacml', 'vomsmap']

IGNORED_OPTIONS = [
    ## pre-3.4 options
    # 'glexec_location',
    # 'enable_cleanup',
    # 'cleanup_age_in_days',
    # 'cleanup_users_list',
    # 'cleanup_cron_time'
]

class MiscConfiguration(BaseConfiguration):
    """Class to handle attributes and configuration related to miscellaneous services"""

    def __init__(self, *args, **kwargs):
        # pylint: disable-msg=W0142
        super(MiscConfiguration, self).__init__(*args, **kwargs)
        self.log('MiscConfiguration.__init__ started')
        self.options = {'glexec_location':
                            configfile.Option(name='glexec_location',
                                              required=configfile.Option.OPTIONAL,
                                              mapping='OSG_GLEXEC_LOCATION'),
                        'gums_host':
                            configfile.Option(name='gums_host',
                                              required=configfile.Option.OPTIONAL),
                        'authorization_method':
                            configfile.Option(name='authorization_method',
                                              default_value='xacml'),
                        'edit_lcmaps_db':
                            configfile.Option(name='edit_lcmaps_db',
                                              required=configfile.Option.OPTIONAL,
                                              opt_type=bool,
                                              default_value=True),
                        'enable_cleanup':
                            configfile.Option(name='enable_cleanup',
                                              required=configfile.Option.OPTIONAL,
                                              opt_type=bool,
                                              default_value=False),
                        'cleanup_age_in_days':
                            configfile.Option(name='cleanup_age_in_days',
                                              required=configfile.Option.OPTIONAL,
                                              opt_type=int,
                                              default_value=14),
                        'cleanup_users_list':
                            configfile.Option(name='cleanup_users_list',
                                              required=configfile.Option.OPTIONAL,
                                              default_value='@vo-file'),
                        'cleanup_cron_time':
                            configfile.Option(name='cleanup_cron_time',
                                              required=configfile.Option.OPTIONAL,
                                              default_value='15 1 * * *'),
                        'copy_host_cert_for_service_certs':
                            configfile.Option(name='copy_host_cert_for_service_certs',
                                              required=configfile.Option.OPTIONAL,
                                              opt_type=bool,
                                              default_value=False)}
        self.config_section = "Misc Services"
        self.htcondor_gateway_enabled = True
        self.authorization_method = None
        self.log('MiscConfiguration.__init__ completed')

    def parse_configuration(self, configuration):
        """
        Try to get configuration information from ConfigParser or SafeConfigParser
        object given by configuration and write recognized settings to options dict
        """
        self.log('MiscConfiguration.parse_configuration started')

        self.check_config(configuration)

        if not configuration.has_section(self.config_section):
            self.enabled = False
            self.log("%s section not in config files" % self.config_section)
            self.log('MiscConfiguration.parse_configuration completed')
            return

        self.enabled = True
        self.get_options(configuration, ignore_options=IGNORED_OPTIONS)

        self.htcondor_gateway_enabled = utilities.config_safe_getboolean(configuration, 'Gateway',
                                                                         'htcondor_gateway_enabled', True)
        self.authorization_method = self.options['authorization_method'].value
        self.using_glexec = not utilities.blank(self.options['glexec_location'].value)

        self.log('MiscConfiguration.parse_configuration completed')

    # pylint: disable-msg=W0613
    def check_attributes(self, attributes):
        """Check attributes currently stored and make sure that they are consistent"""
        self.log('MiscConfiguration.check_attributes started')
        attributes_ok = True

        if not self.enabled:
            self.log('Not enabled, returning True')
            self.log('MiscConfiguration.check_attributes completed')
            return True

        if self.authorization_method not in VALID_AUTH_METHODS:
            self.log("Setting is not one of: " + ", ".join(VALID_AUTH_METHODS),
                     option='authorization_method',
                     section=self.config_section,
                     level=logging.ERROR)
            attributes_ok = False

        if self.authorization_method == 'xacml':
            gums_host = self.options['gums_host'].value
            if utilities.blank(gums_host):
                self.log("Gums host not given",
                         section=self.config_section,
                         option='gums_host',
                         level=logging.ERROR)
                attributes_ok = False
            elif not validation.valid_domain(gums_host, resolve=True):
                self.log("Gums host not a valid domain name or does not resolve",
                         section=self.config_section,
                         option='gums_host',
                         level=logging.ERROR)
                attributes_ok = False

        self.log('MiscConfiguration.check_attributes completed')
        return attributes_ok

    def configure(self, attributes):
        """Configure installation using attributes"""
        self.log('MiscConfiguration.configure started')

        if not self.enabled:
            self.log('Not enabled')
            self.log('MiscConfiguration.configure completed')
            return True

        # run fetch-crl script
        if not utilities.fetch_crl():
            self.log("Error while running fetch-crl script", level=logging.ERROR)
            raise exceptions.ConfigureError('fetch-crl returned non-zero exit code')

        if self.using_glexec and not utilities.rpm_installed('lcmaps-plugins-glexec-tracking'):
            msg = "Can't use glExec because LCMAPS glExec plugin not installed."\
                  " Install lcmaps-plugins-glexec-tracking or unset glexec_location"
            self.log(msg,
                     option='glexec_location',
                     section=self.config_section,
                     level=logging.ERROR)
            raise exceptions.ConfigureError(msg)
        if self.authorization_method == 'xacml':
            self._set_lcmaps_callout(True)
            self._update_gums_client_location()
        elif self.authorization_method == 'gridmap':
            self._set_lcmaps_callout(False)
        elif self.authorization_method == 'local-gridmap':
            self._set_lcmaps_callout(False)
        elif self.authorization_method == 'vomsmap':
            self._set_lcmaps_callout(True)
            if self.using_glexec:
                msg = "glExec not supported with vomsmap authorization; unset glexec_location or change "\
                      " authorization_method"
                self.log(msg,
                         options='glexec_location',
                         section=self.config_section,
                         level=logging.ERROR)
                raise exceptions.ConfigureError(msg)
        else:
            self.log("Unknown authorization method: %s; should be one of: %s" %
                     (self.authorization_method, ", ".join(VALID_AUTH_METHODS)),
                     option='authorization_method',
                     section=self.config_section,
                     level=logging.ERROR)
            raise exceptions.ConfigureError("Invalid authorization_method option in Misc Services")

        if self.options['edit_lcmaps_db'].value:
            self._write_lcmaps_file()
        else:
            self.log("Not updating lcmaps.db because edit_lcmaps_db is false",
                     level=logging.DEBUG)

        if self.htcondor_gateway_enabled:
            self.write_gridmap_to_htcondor_ce_config()

        ensure_valid_user_vo_file(using_gums, gums_host=self.options['gums_host'].value,
                                  logger=self.logger)
        # Call configure_vdt_cleanup (enabling or disabling as necessary)
        self._configure_cleanup()

        self.log('MiscConfiguration.configure completed')
        return True

    def module_name(self):
        """Return a string with the name of the module"""
        return "Misc"

    def separately_configurable(self):
        """Return a boolean that indicates whether this module can be configured separately"""
        return True

    def _set_lcmaps_callout(self, enable):
        self.log("Updating " + GSI_AUTHZ_LOCATION, level=logging.INFO)

        if enable:
            gsi_contents = "globus_mapping liblcas_lcmaps_gt4_mapping.so lcmaps_callout\n"
        else:
            gsi_contents = "#globus_mapping liblcas_lcmaps_gt4_mapping.so lcmaps_callout\n"
        if not utilities.atomic_write(GSI_AUTHZ_LOCATION, gsi_contents):
            msg = "Error while writing to " + GSI_AUTHZ_LOCATION
            self.log(msg, level=logging.ERROR)
            raise exceptions.ConfigureError(msg)

    def _update_gums_client_location(self):
        self.log("Updating " + GUMS_CLIENT_LOCATION, level=logging.INFO)
        location_re = re.compile("^gums.location=.*$", re.MULTILINE)
        authz_re = re.compile("^gums.authz=.*$", re.MULTILINE)
        if not validation.valid_file(GUMS_CLIENT_LOCATION):
            gums_properties = "gums.location=https://%s:8443" % (self.options['gums_host'].value)
            gums_properties += "/gums/services/GUMSAdmin\n"
            gums_properties += "gums.authz=https://%s:8443" % (self.options['gums_host'].value)
            gums_properties += "/gums/services/GUMSXACMLAuthorizationServicePort"
        else:
            gums_properties = open(GUMS_CLIENT_LOCATION).read()
            replacement = "gums.location=https://%s:8443" % (self.options['gums_host'].value)
            replacement += "/gums/services/GUMSAdmin"
            gums_properties = location_re.sub(replacement, gums_properties)
            replacement = "gums.authz=https://%s:8443" % (self.options['gums_host'].value)
            replacement += "/gums/services/GUMSXACMLAuthorizationServicePort"
            gums_properties = authz_re.sub(replacement, gums_properties)
        utilities.atomic_write(GUMS_CLIENT_LOCATION, gums_properties)

    def _write_lcmaps_file(self):
        assert not (self.using_glexec and self.authorization_method == 'vomsmap')

        self.log("Writing " + LCMAPS_DB_LOCATION, level=logging.INFO)
        if self.authorization_method == 'xacml':
            non_glexec_lcmaps_template_fn = lcmaps_template_fn = 'lcmaps.db.gums'
        elif self.authorization_method == 'gridmap' or self.authorization_method == 'local-gridmap':
            non_glexec_lcmaps_template_fn = lcmaps_template_fn = 'lcmaps.db.gridmap'
        elif self.authorization_method == 'vomsmap':
            non_glexec_lcmaps_template_fn = lcmaps_template_fn = 'lcmaps.db.vomsmap'
        else:
            assert False

        if self.using_glexec:
            lcmaps_template_fn += '.glexec'

        lcmaps_template_path = os.path.join(LCMAPS_DB_TEMPLATES_LOCATION, lcmaps_template_fn)
        non_glexec_lcmaps_template_path = os.path.join(LCMAPS_DB_TEMPLATES_LOCATION, non_glexec_lcmaps_template_fn)

        if not validation.valid_file(lcmaps_template_path):
            # Special message if we're using lcmaps from upcoming or 3.4 (which doesn't have the glexec variants):
            if self.using_glexec and validation.valid_file(non_glexec_lcmaps_template_path):
                msg = "glExec lcmaps.db templates not available in this version of lcmaps; unset glexec_location or "\
                      " set edit_lcmaps_db=False"
            else:
                msg = "lcmaps.db template file not found at %s; ensure lcmaps-db-templates is installed or set"\
                      " edit_lcmaps_db=False" % lcmaps_template_path
            self.log(msg, level=logging.ERROR)
            raise exceptions.ConfigureError(msg)

        old_lcmaps_contents = utilities.read_file(LCMAPS_DB_LOCATION, default='')
        if old_lcmaps_contents and 'THIS FILE WAS WRITTEN BY OSG-CONFIGURE' not in old_lcmaps_contents:
            backup_path = LCMAPS_DB_LOCATION + '.pre-configure'
            self.log("Backing up %s to %s" % (LCMAPS_DB_LOCATION, backup_path), level=logging.WARNING)
            try:
                shutil.copy2(LCMAPS_DB_LOCATION, backup_path)
            except EnvironmentError as err:
                msg = "Unable to back up old lcmaps.db: " + str(err)
                self.log(msg, level=logging.ERROR)
                raise exceptions.ConfigureError(msg)

        lcmaps_contents = utilities.read_file(lcmaps_template_path)
        lcmaps_contents = ("# THIS FILE WAS WRITTEN BY OSG-CONFIGURE AND WILL BE OVERWRITTEN ON FUTURE RUNS\n"
                           "# Set edit_lcmaps_db = False in the [%s] section of your OSG configuration to\n"
                           "# keep your changes.\n" % self.config_section
                           + lcmaps_contents.replace('@GUMSHOST@', str(self.options['gums_host'].value)))
        if not utilities.atomic_write(LCMAPS_DB_LOCATION, lcmaps_contents):
            msg = "Error while writing to " + LCMAPS_DB_LOCATION
            self.log(msg, level=logging.ERROR)
            raise exceptions.ConfigureError(msg)

    def _configure_cleanup(self):
        """
        Configure osg-cleanup
        """

        # Do basic error checking to validate that this is a cron string
        if len(re.split(r'\s+', self.options['cleanup_cron_time'].value)) != 5:
            err_msg = "Error: the value of cleanup_cron_time must be a 5 part " \
                      "cron string: %s" % self.options['cleanup_cron_time'].value
            self.log(err_msg,
                     option='cleanup_cron_time',
                     section=self.config_section,
                     level=logging.ERROR)
            raise exceptions.ConfigureError(err_msg)

        filehandle = open('/etc/osg/osg-cleanup.conf', 'w')

        filehandle.write('# This file is automatically generated by osg-configure\n')
        filehandle.write('# Manual modifications to this file may be overwritten\n')
        filehandle.write('# Instead, modify /etc/osg/config.d/10-misc.ini\n')

        filehandle.write('age = %s\n' % (self.options['cleanup_age_in_days'].value))
        filehandle.write('users = %s\n' % (self.options['cleanup_users_list'].value))

        filehandle.close()

        # Writing this file seems a little hacky, but I'm not sure of a better way
        filehandle = open('/etc/cron.d/osg-cleanup', 'w')
        filehandle.write('%s root [ ! -f /var/lock/subsys/osg-cleanup-cron ] || /usr/sbin/osg-cleanup\n' %
                         (self.options['cleanup_cron_time'].value))
        filehandle.close()

        return True

    def enabled_services(self):
        """Return a list of  system services needed for module to work
        """

        if not self.enabled or self.ignored:
            return set()

        services = set()
        if utilities.rpm_installed('fetch-crl'):
            services = set(['fetch-crl-cron', 'fetch-crl-boot'])

        if self.authorization_method == 'xacml':
            services.add('gums-client-cron')
        elif self.authorization_method == 'gridmap':
            services.add('edg-mkgridmap')
        if self.options['enable_cleanup'].value:
            services.add('osg-cleanup-cron')
        return services

    def write_gridmap_to_htcondor_ce_config(self):
        contents = utilities.read_file(HTCONDOR_CE_CONFIG_FILE,
                                       default="# This file is managed by osg-configure\n")
        if 'gridmap' not in self.authorization_method:
            # Remove GRIDMAP setting
            contents = re.sub(r'(?m)^\s*GRIDMAP\s*=.*?$[\n]?', "", contents)
        else:
            contents = utilities.add_or_replace_setting(contents, "GRIDMAP", "/etc/grid-security/grid-mapfile",
                                                        quote_value=False)
        utilities.atomic_write(HTCONDOR_CE_CONFIG_FILE, contents)


def create_user_vo_file(using_gums=False, gums_host=None):
    """
    Check and create a mapfile if needed
    """

    map_file = '/var/lib/osg/user-vo-map'
    try:
        if validation.valid_user_vo_file(map_file):
            return True
        if using_gums:
            try:
                user_vo_file_text = gums_supported_vos.gums_json_user_vo_map_file(gums_host)
                open(USER_VO_MAP_LOCATION, "w").write(user_vo_file_text)
                return True
            except exceptions.ApplicationError, e:
                self.log("Could not query GUMS server via JSON interface: %s" % e, level=logging.DEBUG)

            gums_script = '/usr/bin/gums-host-cron'
        else:
            gums_script = '/usr/sbin/edg-mkgridmap'

        sys.stdout.write("Running %s, this process may take some time " % gums_script +
                         "to query vo and gums servers\n")
        sys.stdout.flush()
        if not utilities.run_script([gums_script]):
            return False
    except IOError:
        return False
    return True


def ensure_valid_user_vo_file(using_gums, gums_host=None, logger=utilities.NullLogger):
    if not validation.valid_user_vo_file(USER_VO_MAP_LOCATION):
        logger.info("Trying to create user-vo-map file")
        result = create_user_vo_file(using_gums, gums_host)
        temp, invalid_lines = validation.valid_user_vo_file(USER_VO_MAP_LOCATION, True)
        result = result and temp
        if not result:
            logger.error("Can't generate user-vo-map, manual intervention is needed")
            if not invalid_lines:
                logger.error("gums-host-cron or edg-mkgridmap generated an empty " +
                             USER_VO_MAP_LOCATION + " file, please check the "
                             "appropriate configuration and or log messages")
                raise exceptions.ConfigureError('Error when generating user-vo-map file')
            logger.error("Invalid lines in user-vo-map file:")
            logger.error("\n".join(invalid_lines))
            raise exceptions.ConfigureError("Error when invoking gums-host-cron or edg-mkgridmap")

