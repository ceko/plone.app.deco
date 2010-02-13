from Products.Five import BrowserView
from zope.component import getUtility
try:
    import json
except:
    import simplejson as json
from plone.autoform.interfaces import IFormFieldProvider
from plone.dexterity.interfaces import IDexterityFTI
from plone.dexterity.utils import resolveDottedName
from plone.registry.interfaces import IRegistry
from plone.app.deco.interfaces import IDecoSettings
from Products.CMFPlone.utils import log
from Acquisition import aq_inner
from plone.tiles.interfaces import ITileType
from Products.CMFCore.interfaces._content import IFolderish
from Products.CMFCore.utils import getToolByName
import base64

def GetBool(value):
    if value == 'False' or value == 'false':
        return False
    else:
        return True

def GetCategoryIndex(tiles, category):
    index = 0
    count = 0
    for tile in tiles:
        if tile['name'] == category:
            index = count
        count += 1
    return index

class DecoUploadView(BrowserView):
    """Handle file uploads"""

    def __call__(self):
        context = self.context
        request = context.REQUEST

        ctr_tool = getToolByName(self.context, 'content_type_registry')
        id = request['uploadfile'].filename

        content_type = request['uploadfile'].headers["Content-Type"]
        typename = ctr_tool.findTypeName(id, content_type, "")

        # 1) check if we are allowed to create an Image in folder 
        if not typename in [t.id for t in context.getAllowedTypes()]: 
            error = {}
            error['status'] = 1
            error['message'] = "Not allowed to upload a file of this type to this folder"
            return json.dumps(error)

        # 2) check if the current user has permissions to add stuff 
        if not context.portal_membership.checkPermission('Add portal content',context): 
            error = {}
            error['status'] = 1
            error['message'] = "You do not have permission to upload files in this folder"
            return json.dumps(error)

        # Get an unused filename without path
        id = self.cleanupFilename(id)

        title = request['uploadfile'].filename

        newid = context.invokeFactory(type_name=typename, id=id)

        if newid is None or newid == '':
            newid = id 

        obj = getattr(context,newid, None)

        # Set title
        # Attempt to use Archetypes mutator if there is one, in case it uses a custom storage
        if title:
            try:
                obj.setTitle(title)
            except AttributeError:
                obj.title = title

        # set primary field
        pf = obj.getPrimaryField()
        pf.set(obj, request['uploadfile'])

        if not obj:
            error = {}
            error['status'] = 1
            error['message'] = "Could not upload the file"
            return json.dumps(error)

        obj.reindexObject()
        message = {}
        message['status'] = 0
        message['url'] = obj.absolute_url()
        message['title'] = title
        return json.dumps(message)

    def cleanupFilename(self, name):
        """Generate a unique id which doesn't match the system generated ids"""

        context = self.context
        id = ''
        name = name.replace('\\', '/') # Fixup Windows filenames
        name = name.split('/')[-1] # Throw away any path part.
        for c in name:
            if c.isalnum() or c in '._':
                id += c

        # Raise condition here, but not a lot we can do about that
        if context.check_id(id) is None and getattr(context,id,None) is None:
            return id

        # Now make the id unique
        count = 1
        while 1:
            if count==1:
                sc = ''
            else:
                sc = str(count)
            newid = "copy%s_of_%s" % (sc, id)
            if context.check_id(newid) is None and getattr(context,newid,None) is None:
                return newid
            count += 1

class DecoConfigView(BrowserView):

    def __call__(self):
        return self.getConfiguration()

    def getConfiguration(self):
        """Get the configuration of current content type"""

        # Get the settings from the Registry
        settings = getUtility(IRegistry).forInterface(IDecoSettings)

        # Create empty configuration
        config = {}

        # Primary / Secondary Actions
        for action_type in ['primary_actions', 'secondary_actions']:
            config[action_type] = []
            for action in getattr(settings, action_type):
                action_fields = action.split('|')
                items = []
                if GetBool(action_fields[6]):
                    for i in range(7, len(action_fields), 2):
                        items.append({
                            'value': action_fields[i],
                            'label': action_fields[i+1]
                        })

                record = {
                    'name': action_fields[0],
                    'label': action_fields[3],
                    'action': action_fields[4],
                    'icon': GetBool(action_fields[5]),
                    'menu': GetBool(action_fields[6]),
                    'items': items
                }

                # If no fieldset
                if action_fields[1] == '':
                    config[action_type].append(record)
    
                # Fieldset
                else:

                    # Find fieldset
                    fieldset_index = -1
                    count = 0
                    for config_action in config[action_type]:
                        if config_action['name'] == action_fields[1]:
                            fieldset_index = count
                        count += 1

                    # Fieldset not found
                    if fieldset_index == -1:
                        config[action_type].append({
                            'name': action_fields[1],
                            'label': action_fields[2],
                            'actions': [record]
                        })

                    # Fieldset not found
                    else:
                        config[action_type][fieldset_index]['actions'].append(record)

        # Formats
        config['formats'] = []

        # Format Categories
        for format_category in settings.format_categories:
            config['formats'].append({
                'name': format_category.split('|')[0],
                'label': format_category.split('|')[1],
                'actions': []
            })

        # Formats
        for format in settings.formats:
            format_fields = format.split('|')
            config['formats'][GetCategoryIndex(config['formats'], format_fields[1])]['actions'].append({
                'name': format_fields[0],
                'label': format_fields[2],
                'action': format_fields[3],
                'icon': GetBool(format_fields[4]),
                'favorite': GetBool(format_fields[5])
            })

        # Default Available Actions
        config['default_available_actions'] = settings.default_available_actions

        # Tiles
        config['tiles'] = []

        # Tile Categories
        for tile_category in settings.tile_categories:
            config['tiles'].append({
                'name': tile_category.split('|')[0],
                'label': tile_category.split('|')[1],
                'tiles': []
            })

        # Structure Tiles
        for structure_tile in settings.structure_tiles:
            tile_fields = structure_tile.split('|')
            config['tiles'][GetCategoryIndex(config['tiles'], tile_fields[1])]['tiles'].append({
                'name': tile_fields[0],
                'label': tile_fields[2],
                'type': tile_fields[3],
                'default_value': tile_fields[4],
                'read_only': GetBool(tile_fields[5]),
                'settings': GetBool(tile_fields[6]),
                'favorite': GetBool(tile_fields[7]),
                'rich_text': GetBool(tile_fields[8]),
                'available_actions': tile_fields[9:-1]
            })

        # Application Tiles
        if settings.app_tiles:
            for app_tile in settings.app_tiles:
                tile_fields = app_tile.split('|')
                config['tiles'][GetCategoryIndex(config['tiles'], tile_fields[1])]['tiles'].append({
                    'name': tile_fields[0],
                    'label': tile_fields[2],
                    'type': 'app',
                    'default_value': '',
                    'read_only': GetBool(tile_fields[3]),
                    'settings': GetBool(tile_fields[4]),
                    'favorite': GetBool(tile_fields[5]),
                    'rich_text': GetBool(tile_fields[6]),
                    'available_actions': tile_fields[7:-1]
                })

        # Field Tiles
        type = self.context.portal_type
        if hasattr(self.context.REQUEST, 'type'):
            type = self.context.REQUEST['type']
        fti = getUtility(IDexterityFTI, name=type)
        for x in fti.lookupSchema():
            pass
            #log(x)

        for behavior_name in fti.behaviors:
            try:
                behavior_interface = resolveDottedName(behavior_name)
            except ValueError:
                continue
            if behavior_interface is not None:
                behavior_schema = IFormFieldProvider(behavior_interface, None)
                if behavior_schema is not None:
                    for x in behavior_schema:
                        pass
                        #log(x)

        config['tiles'].append({
            'name': 'fields',
            'label': 'Fields',
            'tiles': [
                {
                    'name': 'title',
                    'label': 'Title',
                    'type': 'field',
                    'field_type': 'Text line',
                    'widget': 'TextFieldWidget',
                    'tag': 'h1',
                    'id': 'formfield-form-widgets-IDublinCore-title',
                    'read_only': False,
                    'settings': True,
                    'favorite': False,
                    'available_actions': ['tile-align-block', 'tile-align-right', 'tile-align-left']
                },
                {
                    'name': 'description',
                    'label': 'Description',
                    'type': 'field',
                    'field_type': 'Text',
                    'widget': 'TextAreaFieldWidget',
                    'tag': 'p',
                    'id': 'formfield-form-widgets-IDublinCore-description',
                    'read_only': False,
                    'settings': True,
                    'favorite': False,
                    'available_actions': ['tile-align-block', 'tile-align-right', 'tile-align-left']
                },
                {
                    'name': 'date',
                    'label': 'Date',
                    'type': 'field',
                    'field_type': 'Datetime',
                    'widget': 'DateTimePickerFieldWidget',
                    'id': 'formfield-form-widgets-date',
                    'read_only': False,
                    'settings': True,
                    'favorite': False,
                    'available_actions': ['tile-align-block', 'tile-align-right', 'tile-align-left']
                },
                {
                    'name': 'agenda',
                    'label': 'Agenda',
                    'type': 'field',
                    'field_type': 'Text',
                    'widget': 'WysiwygFieldWidget',
                    'id': 'formfield-form-widgets-agenda',
                    'read_only': False,
                    'settings': True,
                    'favorite': False,
                    'available_actions': ['strong', 'em', 'paragraph', 'heading', 'subheading', 'discreet', 'literal', 'quote', 'callout', 'highlight', 'sub', 'sup', 'remove-format', 'pagebreak', 'ul', 'ol', 'justify-left', 'justify-center', 'justify-right', 'justify-justify', 'tile-align-block', 'tile-align-right', 'tile-align-left']
                },
                {
                    'name': 'recurrence',
                    'label': 'Recurrence',
                    'type': 'field',
                    'field_type': 'Choice',
                    'widget': 'SelectFieldWidget',
                    'id': 'formfield-form-widgets-recurrence',
                    'read_only': True,
                    'settings': False,
                    'favorite': False,
                    'rich_text': True,
                    'available_actions': ['tile-align-block', 'tile-align-right', 'tile-align-left']
                }
            ]
        })

        # URLs
        config['document_url'] = self.context.absolute_url()
        if IFolderish.providedBy(self.context):
            config['parent'] = self.context.absolute_url() + "/"
        else:
            config['parent'] = getattr(self.context.aq_inner, 'aq_parent', None).absolute_url() + "/"

        # Write JSON structure
        return json.dumps(config)
