# -*- coding: utf-8 -*-
from __future__ import print_function

import fileinput
import logging
import os
import shutil
import subprocess
import sys
from distutils.version import LooseVersion

import pkg_resources
import zc.buildout
from datetime import datetime
from genshi.template import Context, NewTextTemplate
from genshi.template.base import TemplateSyntaxError
from genshi.template.eval import UndefinedError
from zc.buildout import UserError

import ipdb

#from zc.buildout.easy_install import scripts as create_script


TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'templates')


def system(c):
    if os.system(c):
        raise SystemError("Failed", c)


class _RedmineBaseRecipe(object):

    def __init__(self, buildout, name, options_orig):

        self.buildout, self.name, self.options = buildout, name, options_orig
        self.logger = logging.getLogger(self.name)

        self.options['redmine_version'] = options_orig.get(
            'redmine_version',
            '2.5-stable').strip()
        self.options['virtual-ruby'] = options_orig.get(
            'virtual-ruby',
            False)
        self.options['rails_env'] = options_orig.get(
            'rails_env',
            'production').strip()
        self.options['without'] = options_orig.get(
            'build_without',
            'development test').strip()
        self.options['ruby'] = options_orig.get('ruby', '').strip()

        location = options_orig.get(
            'location', buildout['buildout']['parts-directory'])
        self.options['location'] = os.path.join(location, name)

        self.install_dir = os.path.join(
            buildout['buildout']['parts-directory'], name)

    def _generate_from_template(self, executable=False, **kwargs):
        destination = kwargs['destination']
        source = kwargs['source']
        name = kwargs['name']
        output_file = os.path.join(destination, name)
        with open(source, 'r') as template:
            template = NewTextTemplate(template)

        context = Context(name=name, buildout=self.buildout, options=kwargs)
        try:
            output = template.generate(context).render()
        except (TemplateSyntaxError, UndefinedError) as e:
            raise zc.buildout.UserError("Error in template %s:\n%s" %
                                        (name, e.msg))

        if executable:
            output = '#!%s\n%s' % (sys.executable, output)

        if executable and sys.platform == 'win32':
            exe = output_file + '.exe'
            open(exe, 'wb').write(
                pkg_resources.resource_string('setuptools', 'cli.exe')
            )
            self.generated.append(exe)
            output_file = output_file + '-script.py'

        with open(output_file, 'wb') as outfile:
            outfile.write(output.encode('utf8'))

        if executable:
            self.logger.info("Generated script %r.", name)
            try:
                os.chmod(output_file, 493)  # 0755 / 0o755
            except (AttributeError, os.error):
                pass
        else:
            self.logger.info("Generated file %r.", name)

    def generate_apache_file(self, source, destination, **kwargs):
        gt2_4 = False
        try:
            sub = subprocess.check_output(['apache2ctl', '-v'])
            lines = sub.splitlines()
            for line in lines:
                if line.startswith('Server version: Apache/'):
                    version = line.replace('Server version: Apache/', '')
                    gt2_4 = LooseVersion(version) >= LooseVersion('2.4.0')
        except AttributeError:
            print("no Version Check for Apache possible")

        self._generate_from_template(source=source,
                                     destination=destination,
                                     name='redmine_include.conf',
                                     apache_version_gt2_4=gt2_4,
                                     **kwargs)

    def generate_index_file(self,
                            source,
                            destination,
                            name='index.html',
                            **kwargs):
        self._generate_from_template(source=source,
                                     destination=destination,
                                     name=name,
                                     **kwargs)

    def generate_database_file(self,
                               source,
                               destination,
                               **kwargs):
        self._generate_from_template(source=source,
                                     destination=destination,
                                     name='database.yml',
                                     **kwargs)

    def generate_configuration_file(self,
                                    source,
                                    destination,
                                    **kwargs):
        self._generate_from_template(source=source,
                                     destination=destination,
                                     name='configuration.yml',
                                     **kwargs)


class SingleCoreRecipe(_RedmineBaseRecipe):

    def __init__(self, buildout, name, options):
        super(SingleCoreRecipe, self).__init__(buildout, name, options)

        self.options['redmine_production_db']

    def install(self):
        pass

    def update(self):
        """
        Normally We don't need to do anythin on update -
        install will get called if any of our settings change
        But we allow a workflow for users who wish
        to delete the whole redmine-instance folder and
        recreate it with a buildout update. We do this
        often while testing our application.
        """
        if os.path.exists(self.install_dir):
            pass
        else:
            self.install()


class MultiCoreRecipe(_RedmineBaseRecipe):

    def __init__(self, buildout, name, options):
        super(MultiCoreRecipe, self).__init__(buildout, name, options)

    def install(self):
        logger = logging.getLogger(self.name)
        logger.info('Install Redmine (MultiCore Setup)')
        if os.path.exists(self.options['location']):
            subprocess.call(['rm', '-rf', self.options['location']])

        subprocess.call(['mkdir', '-p', self.options['location']])

        if self.options['virtual-ruby']:
            os.environ['GEM_HOME'] = os.path.join(
                self.options['location'], 'vruby')
            os.environ['GEM_PATH'] = os.path.join(
                self.options['location'], 'vruby', 'gems')
            os.environ['PATH'] = os.environ['GEM_HOME'] + \
                '/bin:' + self.options['ruby'] + ':' + os.environ['PATH']
        else:
            os.environ['GEM_HOME'] = os.path.join(
                self.buildout['buildout']['directory'], 'parts', 'ruby')
            os.environ['GEM_PATH'] = os.path.join(
                self.buildout['buildout']['directory'], 'parts', 'ruby', 'gems')
            #os.environ['PATH'] = self.options['ruby']+':'+os.environ['PATH']
            os.environ['PATH'] = os.environ['GEM_HOME'] + \
                '/bin:' + self.options['ruby'] + ':' + os.environ['PATH']
        os.environ['RAILS_ENV'] = self.options['rails_env']
        os.environ['REDMINE_LANG'] = 'en'

        gems = self.options.get('gems', '').split()
        if gems:
            bin_dir = os.path.abspath(self.options['ruby'])
            self._install_gems(gems, bin_dir)

        try:
            subprocess.call(['svn',
                             'co',
                             'https://svn.redmine.org/redmine/branches/' +
                             self.options['redmine_version'],
                             self.options['location']
                             ])
        except:
            subprocess.call(['rm', '-rf', self.options['location']])

            subprocess.call(['mkdir', '-p', self.options['location']])
            subprocess.call(['git',
                             'clone',
                             'https://github.com/redmine/redmine.git',
                             self.options['location']
                             ],
                            cwd=self.options['location'],
                            env=os.environ)
            subprocess.call(['git',
                             'checkout',
                             self.options['redmine_version']
                             ],
                            cwd=self.options['location'],
                            env=os.environ)

        buildout_var_path = os.path.join(
            self.buildout['buildout']['directory'], 'var')

        instance_list = []
        logger.info('Install Redmine Instances')
        for instance in self.options['instances'].split():
            logger.info('Install Redmine Instance: "' + instance+'"')
            if instance:
                instance_path = os.path.join(
                    self.buildout['buildout']['parts-directory'],
                    'redmine-' + instance)
                buildout_var_path = self.buildout['buildout']['directory'] + \
                    '/var'
                if os.path.exists(instance_path):
                    subprocess.call(['rm', '-fR', instance_path])

                shutil.copytree(self.options['location'], instance_path)

                subprocess.call(
                    ['mkdir',
                     '-p',
                     os.path.join(buildout_var_path, instance, 'files'),
                     os.path.join(buildout_var_path, instance, 'log')])

                subprocess.call(['rm',
                                 '-fR',
                                 os.path.join(instance_path, 'files'),
                                 os.path.join(instance_path, 'log')])

                subprocess.call(
                    ['ln',
                     '-s',
                     os.path.join(buildout_var_path, instance, 'files'),
                     os.path.join(instance_path, 'files')])

                subprocess.call(
                    ['ln',
                     '-s',
                     os.path.join(buildout_var_path, instance, 'log'),
                     os.path.join(instance_path, 'log')])

                self._install_gems(['bundler'], instance_path)
                subprocess.call(
                    ['mkdir',
                     '-p',
                     'tmp',
                     'tmp/pdf',
                     'public/public_assets'],
                    cwd=instance_path,
                    env=os.environ)
                subprocess.call(
                    ['chmod',
                     '-R',
                     '0755',
                     'files',
                     'log',
                     'tmp',
                     'public/public_assets'],
                    cwd=instance_path,
                    env=os.environ)

                # write database file
                redmine_db_config = {}
                if self.buildout[instance].get('redmine_production_db', True):

                    redmine_db_config['production'] = {
                        'adapter': self.buildout[instance].get(
                            'redmine_production_db_adapter',
                            'postgresql'  # alternative: mysql2
                        ),
                        'database': self.buildout[instance].get(
                            'redmine_production_db_database',
                            'redmine-'+instance),
                        'host': self.buildout[instance].get(
                            'redmine_production_db_host',
                            'localhost'),
                        'username': self.buildout[instance].get(
                            'redmine_production_db_username',
                            'redmine'),
                        'password': self.buildout[instance].get(
                            'redmine_production_db_password',
                            'redmine'),
                        'encoding': self.buildout[instance].get(
                            'redmine_production_db_encoding',
                            'utf8'),
                        'port': self.buildout[instance].get(
                            'redmine_production_db_port',
                            ''),
                    }

                if self.buildout[instance].get('redmine_development_db', False):
                    redmine_db_config['development'] = {
                        'adapter':   self.buildout[instance].get(
                            'redmine_development_db_adapter',
                            'postgresql'  # mysql2
                        ),
                        'database': self.buildout[instance].get(
                            'redmine_development_db_database',
                            'redmine-' + instance),
                        'host': self.buildout[instance].get(
                            'redmine_development_db_host',
                            'localhost'),
                        'username': self.buildout[instance].get(
                            'redmine_development_db_username',
                            'redmine'),
                        'password': self.buildout[instance].get(
                            'redmine_development_db_password',
                            'redmine'),
                        'encoding': self.buildout[instance].get(
                            'redmine_development_db_encoding',
                            'utf8'),
                        'port': self.buildout[instance].get(
                            'redmine_development_db_port',
                            ''),
                    }

                if self.buildout[instance].get('redmine_test_db', False):
                    redmine_db_config['test'] = {
                        'adapter': self.buildout[instance].get(
                            'redmine_test_db_adapter',
                            'postgresql'),
                        'database': self.buildout[instance].get(
                            'redmine_test_db_database',
                            'redmine-' + instance),
                        'host': self.buildout[instance].get(
                            'redmine_test_db_host',
                            'localhost'),
                        'username': self.buildout[instance].get(
                            'redmine_test_db_username',
                            'redmine'),
                        'password': self.buildout[instance].get(
                            'redmine_test_db_password',
                            'redmine'),
                        'encoding': self.buildout[instance].get(
                            'redmine_test_db_encoding',
                            'utf8'),
                        'port': self.buildout[instance].get(
                            'redmine_test_db_port',
                            ''),
                    }

                self.generate_database_file(
                    source=('%s/database.yml.tmpl' % TEMPLATE_DIR),
                    destination=os.path.join(instance_path, 'config'),
                    db_config = redmine_db_config,
                )

                # Test if db alread loaded
                data_db_flag_file = os.path.join(buildout_var_path,
                                                 instance,
                                                 'db_flag_file')
                if not os.path.exists(data_db_flag_file):
                    # treat as database did not exist
                    # and create DB and run imports

                    for db in redmine_db_config.keys():
                        if redmine_db_config[db]['adapter'] == 'postgresql':
                            command = [
                                'createdb', redmine_db_config[db]['database'],
                                '-h', redmine_db_config[db]['host'],
                                '-U', redmine_db_config[db]['username'],
                                '-W',
                                '-O', redmine_db_config[db]['username'],
                                '-E', redmine_db_config[db]['encoding']
                            ]
                            #if redmine_db_config[db]['port']:
                            #    command.append('-p')
                            #    command.append(redmine_db_config[db]['port'])

                            #import ipdb; ipdb.set_trace()
                            subprocess.call(command)
                        elif redmine_db_config[db]['adapter'] == 'mysql2':
                            subprocess.call([
                                'mysql',
                                '-u', redmine_db_config[db]['username'],
                                '-p', redmine_db_config[db]['password'],
                                '-e', '"create database {db_name}"'
                                .format(
                                    db_name=redmine_db_config[db]['database'])
                            ])
                        else:
                            self.logger.warn('unknown database adapter')

                    self._bundle_install(instance_path)
                    subprocess.call(['rake', 'generate_secret_token'],
                                    cwd=instance_path,
                                    env=os.environ)

                    subprocess.call(['rake', 'db:migrate'],
                                    cwd=instance_path,
                                    env=os.environ)
                    subprocess.call(['rake', 'redmine:load_default_data'],
                                    cwd=instance_path,
                                    env=os.environ)
                    flag_file = open(data_db_flag_file, 'w')
                    flag_file.write(str(datetime.now()))
                else:  # if DB exists: just rebuild and run migrate to update DB
                    self._bundle_install(instance_path)

                    # Generate a Secret Token for Cookie encryption and Session
                    subprocess.call(['rake', 'generate_secret_token'],
                                    cwd=instance_path,
                                    env=os.environ)

                    # General Database Migration
                    subprocess.call(['rake', 'db:migrate'],
                                    cwd=instance_path,
                                    env=os.environ)

                # Build config/configuration.yml
                config = {}

                if self.buildout[instance].get('secret_token'):
                    config['use_secret_token'] = True
                    config['secret_token'] = self.buildout[instance].get(
                        'secret_token')
                else:
                    config['use_secret_token'] = False

                self.generate_configuration_file(
                    source=('%s/configuration.yml.tmpl' % TEMPLATE_DIR),
                    destination=os.path.join(instance_path, 'config'),
                    config = config,
                )

                # install Themes and Plugins by linking
                plugin_source_path = os.path.abspath(
                    self.options.get('plugins-location'))
                theme_source_path = os.path.abspath(
                    self.options.get('themes-location'))

                plugin_path = os.path.join(instance_path, 'plugins')
                theme_path = os.path.join(instance_path, 'public', 'themes')

                selected_plugins = self.buildout[instance].get(
                    'plugins', '').split()
                selected_themes = self.buildout[instance].get(
                    'themes', '').split()

                missing_plugins = set(selected_plugins) - set(
                    os.listdir(plugin_source_path))
                if missing_plugins:
                    raise UserError(
                        ', '.join(missing_plugins) + ' not found')
                else:
                    for plugin in selected_plugins:

                        shutil.copytree(
                            os.path.abspath(
                                os.path.join(plugin_source_path, plugin)
                            ),
                            os.path.join(plugin_path, plugin))

                missing_themes = set(selected_themes) - set(
                    os.listdir(theme_source_path))
                if missing_themes:
                    raise UserError(
                        ', '.join(missing_themes) + ' not found')
                else:
                    for theme in selected_themes:
                        shutil.copytree(
                            os.path.abspath(
                                os.path.join(theme_source_path, theme)
                            ),
                            os.path.join(theme_path, theme))

                self._bundle_install(instance_path)

                # General Database migration
                subprocess.call(['rake', 'db:migrate'],
                                cwd=instance_path,
                                env=os.environ)

                # General Plugin migration
                subprocess.call(['rake', 'redmine:plugins'],
                                cwd=instance_path,
                                env=os.environ)

                subprocess.call(['rake', 'redmine:plugins:migrate'],
                                cwd=instance_path,
                                env=os.environ)

                for plugin in [f for f in os.listdir(plugin_path) if
                               os.path.isdir(os.path.join(plugin_path, f))]:

                    subprocess.call(['rake', 'redmine:plugins', 'NAME='+plugin],
                                    cwd=instance_path,
                                    env=os.environ)

                # Clear Redmine Cache
                subprocess.call(['rake', 'tmp:cache:clear'],
                                cwd=instance_path,
                                env=os.environ)

                # Clear Redmine Session Store
                subprocess.call(['rake', 'tmp:session:clear'],
                                cwd=instance_path,
                                env=os.environ)

                # Build Dictionary for Apache Config
                ainstance = {}
                ainstance['suburi'] = self.buildout[instance].get(
                    'sub_uri', '/' + instance)
                ainstance['location'] = instance_path
                ainstance['gem_home'] = os.environ['GEM_HOME']
                ainstance['gem_path'] = os.environ['GEM_PATH']
                instance_list.append(ainstance)

                logger.info(
                    'Installation completed (Instance: "' + instance + '"")')

        logger.info("Installation of instances completed, generate Meta-Files")
        passenger_ruby = self.options['ruby']+'/ruby'

        self.generate_apache_file(
            source=('%s/apache_include.tmpl' % TEMPLATE_DIR),
            destination=os.path.abspath(self.buildout['buildout']['directory']),
            mc = True,
            instances = instance_list,
            ruby = passenger_ruby
        )

        self.generate_index_file(
            source=('%s/index.html.mc.tmpl' % TEMPLATE_DIR),
            destination=os.path.abspath(self.buildout['buildout']['directory']),
            instances = instance_list,
        )

        self.generate_index_file(
            source=('%s/index.html.incl.tmpl' % TEMPLATE_DIR),
            destination=os.path.abspath(self.buildout['buildout']['directory']),
            name='index.html.incl',
            instances = instance_list,
        )

        logger.info('Installation of Redmine completed.')
        return self.options['location']

    def update(self):
        """
        Normally We don't need to do anythin on update -
        install will get called if any of our settings change
        But we allow a workflow for users who wish
        to delete the whole redmine-instance folder and
        recreate it with a buildout update. We do this
        often while testing our application.
        """
        self.install()
        #if os.path.exists(self.install_dir):
        #    pass
        #else:
        #    self.install()

    def _install_gems(self, gems=[], working_dir='.'):
        if gems:
            self.logger.info(
                'Install Ruby Gems: {gems}'.format(
                    gems=' '.join(gems)))
            if os.environ.get('https_proxy'):
                subprocess.call(['gem',
                                 'install',
                                 '--http-proxy='+os.environ['https_proxy'],
                                 '--source=https://rubygems.org/']+gems,
                                cwd=working_dir,
                                env=os.environ)

            elif os.environ.get('http_proxy'):
                subprocess.call(['gem',
                                 'install',
                                 '--http-proxy='+os.environ['http_proxy'],
                                 '--source=http://rubygems.org/']+gems,
                                cwd=working_dir,
                                env=os.environ)
            else:
                subprocess.call(['gem', 'install']+gems,
                                cwd=working_dir,
                                env=os.environ)

    def _bundle_install(self, working_dir='.'):
        if os.environ.get('http_proxy') and \
                os.environ.get('https_proxy') and \
                (os.environ.get('http_proxy') != os.environ.get('https_proxy')):
            self._modify_gemfiles(working_dir)

        #subprocess.call(['which', 'bundle'],
        #                cwd=working_dir,
        #                env=os.environ)

        subprocess.call(['bundle',
                        'install',
                        '--without'] +
                        self.options['without'].split(),
                        cwd=working_dir,
                        env=os.environ)

    def _modify_gemfiles(self, working_dir):
        gemfiles = [os.path.join(working_dir, 'Gemfile')]
        for plugin in os.listdir(os.path.join(working_dir, 'plugins')):
            gemfiles.append(
                os.path.join(working_dir, 'plugins', plugin, 'Gemfile'))

        self.logger.info(
            'Change Gemfiles: {gemfiles}'.format(
                gemfiles=' '.join(gemfiles)))

        for gemfile in gemfiles:
            if os.path.exists(gemfile):
                for line in fileinput.input(gemfile, inplace=True):
                    print(
                        line.replace(
                            "source 'https://rubygems.org'",
                            "source 'http://rubygems.org'"),
                        end='')
