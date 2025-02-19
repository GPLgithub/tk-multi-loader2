# Copyright (c) 2015 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import sgtk
from sgtk.platform.qt import QtCore, QtGui

from . import utils, constants

# import the shotgun_model module from the shotgun utils framework
shotgun_model = sgtk.platform.import_framework(
    "tk-framework-shotgunutils", "shotgun_model"
)
ShotgunModel = shotgun_model.ShotgunModel


class SgPublishHistoryModel(ShotgunModel):
    """
    This model represents the version history for a publish.
    """

    USER_THUMB_ROLE = QtCore.Qt.UserRole + 101
    PUBLISH_THUMB_ROLE = QtCore.Qt.UserRole + 102

    def __init__(self, parent, bg_task_manager):
        """
        Constructor
        """
        # folder icon
        self._loading_icon = QtGui.QPixmap(":/res/loading_100x100.png")
        app = sgtk.platform.current_bundle()
        self._use_version_thumbnail_as_fallback = app.get_setting(
            "use_version_thumbnail_as_fallback"
        )
        ShotgunModel.__init__(
            self,
            parent,
            download_thumbs=app.get_setting("download_thumbnails"),
            schema_generation=2,
            bg_load_thumbs=True,
            bg_task_manager=bg_task_manager,
        )

    ############################################################################################
    # public interface

    def load_data(self, sg_data):
        """
        Load the details for the shotgun publish entity described by sg_data.

        :param sg_data: dictionary describing a publish in shotgun, including all the common
                        publish fields.
        """

        app = sgtk.platform.current_bundle()
        publish_entity_type = sgtk.util.get_published_file_entity_type(app.sgtk)

        if publish_entity_type == "PublishedFile":
            publish_type_field = "published_file_type"
        else:
            publish_type_field = "tank_type"

        # fields to pull down
        fields = [publish_type_field] + constants.PUBLISHED_FILES_FIELDS + app.get_setting("published_file_fields", [])

        # When we filter out which other publishes are associated with this one,
        # to effectively get the "version history", we look for items
        # based on the publish_history_group_by_fields setting.
        # By default, it finds Published Files with the same
        # project, task, entity, name and published_file_type.
        group_by_fields = app.get_setting("publish_history_group_by_fields", [])
        filters = []
        for field in group_by_fields:
            filters.append([field, "is", sg_data[field]])

        # add external filters from config
        app = sgtk.platform.current_bundle()
        pub_filters = app.get_setting("publish_filters", [])
        filters.extend(pub_filters)

        ShotgunModel._load_data(
            self,
            entity_type=publish_entity_type,
            filters=filters,
            hierarchy=["version_number"],
            fields=fields,
        )

        self._refresh_data()

    def async_refresh(self):
        """
        Refresh the current data set
        """
        self._refresh_data()

    ############################################################################################
    # subclassed methods

    def _item_created(self, item):
        """
        Called when an item is created, before it is added to the model.

        Override default behavior to only download thumbnails for the fields
        we're interested in, and avoid downloading preview images when no
        actual image is available.

        :param item: The item that was just created.
        :type item: :class:`~PySide.QtGui.QStandardItem`
        """
        # We call the ShotgunModel base implementation
        # since we want to completely override the default
        # behavior.
        super(ShotgunModel, self)._item_created(item)

        # request thumbnail for this item
        if sgtk.platform.current_bundle().get_setting("download_thumbnails"):
            sg_data = item.data(self.SG_DATA_ROLE)
            if sg_data:
                image_field = utils.get_thumbnail_field_for_item(item, self._use_version_thumbnail_as_fallback)
                if image_field:
                    self._request_thumbnail_download(
                        item,
                        image_field,
                        sg_data[image_field],
                        sg_data.get("type"),
                        sg_data.get("id"),
                    )

    def _populate_item(self, item, sg_data):
        """
        Whenever an item is constructed, this methods is called. It allows subclasses to intercept
        the construction of a QStandardItem and add additional metadata or make other changes
        that may be useful. Nothing needs to be returned.

        :param item: QStandardItem that is about to be added to the model. This has been primed
                     with the standard settings that the ShotgunModel handles.
        :param sg_data: Shotgun data dictionary that was received from Shotgun given the fields
                        and other settings specified in load_data()
        """

        # note that when the sg model creates the name field for each item,
        # it creates a string value. In our case, we use version number as the name
        # and use this for automatic sorting, meaning that QT will auto sort
        # "1", "10", "2" etc instead of proper integer sorting. Avoid this by
        # force setting the name field to a three zero padded string instead to
        # reflect how values are displayed.
        # Also note that since we use a delegate for data display, this value is
        # only used for sorting, not for display.
        if sg_data.get("version_number"):
            item.setText("%03d" % sg_data.get("version_number"))

        # see if we can get a thumbnail for the user
        if sg_data.get("created_by.HumanUser.image"):
            # get the thumbnail - store the unique id we get back from
            # the data retrieve in a dict for fast lookup later
            self._request_thumbnail_download(
                item,
                "created_by.HumanUser.image",
                sg_data["created_by.HumanUser.image"],
                sg_data["created_by"]["type"],
                sg_data["created_by"]["id"],
            )

    def _before_data_processing(self, sg_data_list):
        """
        Called just after data has been retrieved from Shotgun but before any processing
        takes place. This makes it possible for deriving classes to perform summaries,
        calculations and other manipulations of the data before it is passed on to the model
        class.

        :param sg_data_list: list of shotgun dictionaries, as returned by the find() call.
        :returns: should return a list of shotgun dictionaries, on the same form as the input.
        """
        app = sgtk.platform.current_bundle()

        return utils.filter_publishes(app, sg_data_list)

    def _populate_default_thumbnail(self, item):
        """
        Called whenever an item needs to get a default thumbnail attached to a node.
        When thumbnails are loaded, this will be called first, when an object is
        either created from scratch or when it has been loaded from a cache, then later
        on a call to _populate_thumbnail will follow where the subclassing implementation
        can populate the real image.
        """
        # set up publishes with a "thumbnail loading" icon
        item.setData(self._loading_icon, SgPublishHistoryModel.PUBLISH_THUMB_ROLE)
        thumb = utils.create_overlayed_user_publish_thumbnail(
            item.data(SgPublishHistoryModel.PUBLISH_THUMB_ROLE), None
        )
        item.setIcon(QtGui.QIcon(thumb))

    def _populate_thumbnail_image(self, item, field, image, path):
        """
        Called whenever a thumbnail for an item has arrived on disk. In the case of
        an already cached thumbnail, this may be called very soon after data has been
        loaded, in cases when the thumbs are downloaded from Shotgun, it may happen later.

        This method will be called only if the model has been instantiated with the
        download_thumbs flag set to be true. It will be called for items which are
        associated with shotgun entities (in a tree data layout, this is typically
        leaf nodes).

        This method makes it possible to control how the thumbnail is applied and associated
        with the item. The default implementation will simply set the thumbnail to be icon
        of the item, but this can be altered by subclassing this method.

        Any thumbnails requested via the _request_thumbnail_download() method will also
        resurface via this callback method.

        :param item: QStandardItem which is associated with the given thumbnail
        :param field: The Shotgun field which the thumbnail is associated with.
        :param path: A path on disk to the thumbnail. This is a file in jpeg format.
        """
        image_field = utils.get_thumbnail_field_for_item(item, self._use_version_thumbnail_as_fallback)
        # There are only two images used in the model, the Published File thumbnail and the user thumbnail.
        # This method in theory will be called only for these fields, since there are the only ones we request
        # a download for. But just in case, we only populate the thumbnail image for the fields we expect.
        if image_field and field == image_field:
            thumb = QtGui.QPixmap.fromImage(image)
            item.setData(thumb, SgPublishHistoryModel.PUBLISH_THUMB_ROLE)
        # created_by.HumanUser.image is the only image field that can represent a user thumbnail.
        elif field == "created_by.HumanUser.image":
            thumb = QtGui.QPixmap.fromImage(image)
            item.setData(thumb, SgPublishHistoryModel.USER_THUMB_ROLE)

        # composite the user thumbnail and the publish thumb into a single image
        thumb = utils.create_overlayed_user_publish_thumbnail(
            item.data(SgPublishHistoryModel.PUBLISH_THUMB_ROLE),
            item.data(SgPublishHistoryModel.USER_THUMB_ROLE),
        )
        item.setIcon(QtGui.QIcon(thumb))
