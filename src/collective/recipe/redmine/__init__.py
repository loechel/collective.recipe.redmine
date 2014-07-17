# -*- coding: utf-8 -*-

from genshi.template import Context, NewTextTemplate
from genshi.template.base import TemplateSyntaxError
from genshi.template.eval import UndefinedError

from datetime import datetime

from zc.buildout.easy_install import scripts as create_script
from zc.buildout import UserError

import glob
import logging
import os
import shutil
import sys
import subprocess

import pkg_resources
import zc.buildout


TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'templates')

def system(c):
    if os.system(c):
        raise SystemError("Failed", c)

class _RedmineBaseRecipe(object):

    def __init__(self, buildout, name, options_orig):

        self.buildout, self.name, self.options = buildout, name, options_orig

        #self.options = {}

        self.options['redmine_version'] = options_orig.get('redmine_version', '2.5-stable').strip()
        self.options['virtual-ruby'] = options_orig.get('virtual-ruby', False)
        self.options['rails_env'] = options_orig.get('rails_env', 'production').strip()
        self.options['without'] = options_orig.get('build_without', 'development test').strip()
        self.options['ruby'] = options_orig.get('ruby', '').strip()

        location = options_orig.get(
            'location', buildout['buildout']['parts-directory'])
        self.options['location'] = os.path.join(location, name)

        self.install_dir = os.path.join(
            buildout['buildout']['parts-directory'], name)

        self.logger = logging.getLogger(self.name)

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
        self._generate_from_template(source=source, destination=destination,
                                     name='redmine_include.conf', **kwargs)
    def generate_index_file(self, source, destination, **kwargs):
        self._generate_from_template(source=source, destination=destination,
                                     name='index.html', **kwargs)
    def generate_database_file(self, source, destination, **kwargs):
        self._generate_from_template(source=source, destination=destination,
                                     name='database.yml', **kwargs)

class SingleCoreRecipe(_RedmineBaseRecipe):

    def __init__(self, buildout, name, options):
        super(SingleCoreRecipe, self).__init__(buildout, name, options)

        self.options['redmine_production_db']

    def install(self):
        logger = logging.getLogger(self.name)
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

        system('mkdir -p {path}'.format(path=self.options['location']))
        system('cd {path}'.format(path=self.options['location']))

        if self.options['virtual-ruby']:
            os.environ['GEM_HOME'] = os.path.join(self.options['location'],'vruby')
            os.environ['GEM_PATH'] = os.path.join(self.options['location'],'vruby','gems')
            os.environ['PATH'] = os.environ['GEM_HOME']+'/bin:'+self.options['ruby']+':'+os.environ['PATH']
        else:
            os.environ['GEM_HOME'] = os.path.join(self.buildout['buildout']['directory'], 'parts', 'ruby')
            os.environ['GEM_PATH'] = os.path.join(self.buildout['buildout']['directory'], 'parts', 'ruby', 'gems')
            #os.environ['PATH'] = self.options['ruby']+':'+os.environ['PATH']
            os.environ['PATH'] = os.environ['GEM_HOME']+'/bin:'+self.options['ruby']+':'+os.environ['PATH']
        os.environ['RAILS_ENV'] = self.options['rails_env']
        os.environ['REDMINE_LANG'] = 'en'

        gems = self.options.get('gems', '').split()
        if gems:
            bin_dir = os.path.abspath(self.options['ruby'])

            logger.info('Install Ruby Gems: {gems}'.format(gems=' '.join(gems)))
            subprocess.call(['gem', 'install']+gems, cwd=self.options['location'], env=os.environ)

        system('svn co http://svn.redmine.org/redmine/branches/{version} {path}'.format(version=self.options['redmine_version'], path=self.options['location']))

        buildout_var_path=os.path.join(self.buildout['buildout']['directory'], 'var')

        instance_list = []

        for instance in self.options['instances'].split():
            if instance:
                instance_path = os.path.join(self.buildout['buildout']['parts-directory'], 'redmine-'+instance)
                buildout_var_path=self.buildout['buildout']['directory']+'/var'
                if os.path.exists(instance_path):
                    system('rm -fR '+instance_path)
                system('mkdir -p {instance_path}'.format(instance_path=instance_path))
                system('cp -Rf {org_path}/* {instance_path}/.'.format(org_path=self.options['location'],instance_path=instance_path))

                system('mkdir -p {buildout_var_path}/{instance_name}/files {buildout_var_path}/{instance_name}/log'.format(
                    buildout_var_path=buildout_var_path,
                    instance_name=instance
                    ))

                system('rm -fR {instance_path}/files {instance_path}/log'.format(instance_path=instance_path))
                system('ln -s {buildout_var_path}/{instance_name}/files {instance_path}/files'.format(
                    buildout_var_path=buildout_var_path,
                    instance_name=instance,
                    instance_path=instance_path
                    ))
                system('ln -s {buildout_var_path}/{instance_name}/log {instance_path}/log'.format(
                    buildout_var_path=buildout_var_path,
                    instance_name=instance,
                    instance_path=instance_path
                    ))

                subprocess.call(['gem', 'install', 'bundler'], cwd=instance_path, env=os.environ)
                subprocess.call(['mkdir', '-p', 'tmp', 'tmp/pdf', 'public/public_assets'], cwd=instance_path, env=os.environ)
                subprocess.call(['chmod', '-R', '0755', 'files', 'log', 'tmp', 'public/public_assets'], cwd=instance_path, env=os.environ)

                # write database file
                redmine_db_config = {}
                if self.buildout[instance].get('redmine_production_db'):

                    redmine_db_config['production'] = {
                        'adapter'  : self.buildout[instance].get('redmine_production_db_adapter','postgresql'), #mysql2)
                        'database' : self.buildout[instance].get('redmine_production_db_database', 'redmine-'+instance),
                        'host'     : self.buildout[instance].get('redmine_production_db_host','localhost'),
                        'username' : self.buildout[instance].get('redmine_production_db_username','redmine'),
                        'password' : self.buildout[instance].get('redmine_production_db_password','redmine'),
                        'encoding' : self.buildout[instance].get('redmine_production_db_encoding','utf8'),
                        }

                    port = self.buildout[instance].get('redmine_production_db_port', ''), # '3306','5432'
                    if port:
                        redmine_db_config['production']['port'] = port
                if self.buildout[instance].get('redmine_development_db'):
                    redmine_db_config['development'] = {
                        'adapter'  : self.buildout[instance].get('redmine_development_db_adapter','postgresql'), #mysql2)
                        'database' : self.buildout[instance].get('redmine_development_db_database', 'redmine-'+instance),
                        'host'     : self.buildout[instance].get('redmine_development_db_host','localhost'),
                        'username' : self.buildout[instance].get('redmine_development_db_username','redmine'),
                        'password' : self.buildout[instance].get('redmine_development_db_password','redmine'),
                        'encoding' : self.buildout[instance].get('redmine_development_db_encoding','utf8'),
                        }
                    port = self.buildout[instance].get('redmine_development_db_port'), # '3306','5432'
                    if port:
                        redmine_db_config['development']['port'] = port
                if self.buildout[instance].get('redmine_test_db'):
                    redmine_db_config['test'] = {
                        'adapter'  : self.buildout[instance].get('redmine_test_db_adapter','postgresql'), #mysql2)
                        'database' : self.buildout[instance].get('redmine_test_db_database', 'redmine-'+instance),
                        'host'     : self.buildout[instance].get('redmine_test_db_host','localhost'),
                        'username' : self.buildout[instance].get('redmine_test_db_username','redmine'),
                        'password' : self.buildout[instance].get('redmine_test_db_password','redmine'),
                        'encoding' : self.buildout[instance].get('redmine_test_db_encoding','utf8'),
                        }
                    port = self.buildout[instance].get('redmine_test_db_port'), # '3306','5432'
                    if port:
                        redmine_db_config['test']['port'] = port


                self.generate_database_file(            
                    source=('%s/database.yml.tmpl' % TEMPLATE_DIR),                    
                    destination=os.path.join(instance_path, 'config'),
                    db_config = redmine_db_config,
                    )



                # Test if db alread loaded
                data_db_flag_file = os.path.join(buildout_var_path, instance, 'db_flag_file')
                if not os.path.exists(data_db_flag_file):
                    # treat as database did not exist and create DB and run imports
                    
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
                                '-e', '"create database {db_name}"'.format(db_name=redmine_db_config[db]['database'])
                                ])
                        else:
                            self.logger.warn('unknown database adapter')


                    subprocess.call(['bundle', 'install', '--without']+self.options['without'].split(), cwd=instance_path, env=os.environ)
                    subprocess.call(['rake', 'generate_secret_token'], cwd=instance_path, env=os.environ)

                    subprocess.call(['rake', 'db:migrate'], cwd=instance_path, env=os.environ)
                    subprocess.call(['rake', 'redmine:load_default_data'], cwd=instance_path, env=os.environ)
                    flag_file = open(data_db_flag_file, 'w')
                    flag_file.write(str(datetime.now()))
                else:
                    # if DB exists: just rebuild and run migrate to update DB

                    subprocess.call(['bundle', 'install', '--without']+self.options['without'].split(), cwd=instance_path, env=os.environ)
                    subprocess.call(['rake', 'generate_secret_token'], cwd=instance_path, env=os.environ)
                    subprocess.call(['rake', 'db:migrate'], cwd=instance_path, env=os.environ)


                # install Themes and Plugins by linking
                plugin_source_path = os.path.abspath(self.buildout[instance].get('plugins'))
                theme_source_path = os.path.abspath(self.buildout[instance].get('themes'))

                plugin_path = os.path.join(instance_path, 'plugins')
                theme_path = os.path.join(instance_path, 'public', 'themes')

                for plugin in os.listdir(plugin_source_path):
                    os.symlink(os.path.abspath(os.path.join(plugin_source_path, plugin)), os.path.join(plugin_path, plugin))

                for theme in os.listdir(theme_source_path):
                    os.symlink(os.path.abspath(os.path.join(theme_source_path, theme)), os.path.join(theme_path, theme))

                subprocess.call(['bundle', 'install', '--without']+self.options['without'].split(), cwd=instance_path, env=os.environ)
                subprocess.call(['rake', 'db:migrate'], cwd=instance_path, env=os.environ)

                subprocess.call(['rake', 'redmine:plugins'], cwd=instance_path, env=os.environ)
                subprocess.call(['rake', 'redmine:plugins:migrate'], cwd=instance_path, env=os.environ)

                for plugin in [f for f in os.listdir(plugin_path) if os.path.isdir(os.path.join(plugin_path, f))]:
                    subprocess.call(['rake', 'redmine:plugins', 'NAME='+plugin], cwd=instance_path, env=os.environ)

                subprocess.call(['rake', 'tmp:cache:clear'], cwd=instance_path, env=os.environ)
                subprocess.call(['rake', 'tmp:session:clear'], cwd=instance_path, env=os.environ)



                ainstance = {}
                ainstance['suburi'] = self.buildout[instance].get('redmine_suburi')
                ainstance['location'] = instance_path
                ainstance['gem_home'] = os.environ['GEM_HOME']
                ainstance['gem_path'] = os.environ['GEM_PATH']
                instance_list.append(ainstance)


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
