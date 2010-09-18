from Products.Five import BrowserView
from zope.component import getUtility
try:
    import json
except:
    import simplejson as json

from plone.registry.interfaces import IRegistry
from plone.app.deco.interfaces import IDecoRegistryAdapter
from Products.CMFCore.utils import getToolByName

from plone.app.deco import PloneMessageFactory as _


class DecoUploadView(BrowserView):
    """Handle file uploads"""

    def __call__(self):
        context = self.context
        request = context.REQUEST

        # Set header to json
        self.request.RESPONSE.setHeader('Content-Type', 'application/json')

        ctr_tool = getToolByName(self.context, 'content_type_registry')
        id = request['uploadfile'].filename

        content_type = request['uploadfile'].headers["Content-Type"]
        typename = ctr_tool.findTypeName(id, content_type, "")

        # 1) check if we are allowed to create an Image in folder
        if not typename in [t.id for t in context.getAllowedTypes()]:
            error = {}
            error['status'] = 1
            error['message'] =\
                _(u"Not allowed to upload a file of this type to this folder")
            return json.dumps(error)

        # 2) check if the current user has permissions to add stuff
        if not context.portal_membership.checkPermission('Add portal content',
                                                         context):
            error = {}
            error['status'] = 1
            error['message'] =\
                _(u"You do not have permission to upload files in this folder")
            return json.dumps(error)

        # Get an unused filename without path
        id = self.cleanupFilename(id)

        title = request['uploadfile'].filename

        newid = context.invokeFactory(type_name=typename, id=id)

        if newid is None or newid == '':
            newid = id

        obj = getattr(context, newid, None)

        # Set title
        # Attempt to use Archetypes mutator if there is one,
        # in case it uses a custom storage
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
            error['message'] = _(u"Could not upload the file")
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
        name = name.replace('\\', '/')  # Fixup Windows filenames
        name = name.split('/')[-1]  # Throw away any path part.
        for c in name:
            if c.isalnum() or c in '._':
                id += c

        # Raise condition here, but not a lot we can do about that
        if context.check_id(id) is None and getattr(context, id, None) is None:
            return id

        # Now make the id unique
        count = 1
        while 1:
            if count == 1:
                sc = ''
            else:
                sc = str(count)
            newid = "copy%s_of_%s" % (sc, id)
            if context.check_id(newid) is None\
                and getattr(context, newid, None) is None:
                return newid
            count += 1


class DecoConfigView(BrowserView):

    def obtain_type(self):
        """
        Obtains the type of the context object or of the object we are adding
        """
        if 'type' in self.request.form:
            return self.request.form['type']
        else:
            if hasattr(self.context, 'portal_type'):
                return self.context.portal_type
        return None

    def __call__(self):
        self.request.RESPONSE.setHeader('Content-Type', 'application/json')
        registry = getUtility(IRegistry)
        adapted = IDecoRegistryAdapter(registry)
        kwargs = {
            'type': self.obtain_type(),
            'context': self.context,
            'request': self.request,
        }
        return json.dumps(adapted(**kwargs))
