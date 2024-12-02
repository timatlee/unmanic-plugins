#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging

from unmanic.libs.unplugins.settings import PluginSettings

# Configure plugin logger
logger = logging.getLogger("Unmanic.Plugin.resize_video")

from resize_video.lib.ffmpeg import StreamMapper, Probe, Parser


class Settings(PluginSettings):
    settings = {
        "Force aspect ratio": False,
        "Resolution": "720",
    }

    form_settings = {
            "Force aspect ratio": {
                "label": "Force a 16:9 aspect ratio (1920x1080, 1280x720, etc). If not selected, will scale the horizontal resolution to maintain aspect ratio."
            },
            "Resolution": {
                "input_type": "select",
                "label": "Set a vertical resolutoin",
                "select_options": [
                    {
                        'value': "720",
                        'label': "HD (1280x720)",
                    },
                    {
                        'value': "1080",
                        'label': "Full HD (1920x1080)",
                    },
                    {
                        'value': "1440",
                        'label': "Quad HD (2560x1440)",
                    },
                    {
                        'value': "2160",
                        'label': "Ultra HD (3840x2160)",
                    }
                ],
            },
    }


    def __init__(self, *args, **kwargs):
        super(Settings, self).__init__(*args, **kwargs)

def on_library_management_file_test(data):
    """
    Runner function - enables additional actions during the library management file tests.
    The 'data' object argument includes:
        library_id                      - The library that the current task is associated with
        path                            - String containing the full path to the file being tested.
        issues                          - List of currently found issues for not processing the file.
        add_file_to_pending_tasks       - Boolean, is the file currently marked to be added to the queue for processing.
        priority_score                  - Integer, an additional score that can be added to set the position of the new task in the task queue.
        shared_info                     - Dictionary, information provided by previous plugin runners. This can be appended to for subsequent runners.
    :param data:
    :return:
    """

    # Get the path to the file
    abspath = data.get('path')

    # Get file probe
    probe = Probe(logger)
    if not probe.file(abspath):
        # File probe failed, skip the rest of this test
        return data

    # Configure settings object (maintain compatibility with v1 plugins)
    if data.get('library_id'):
        settings = Settings(library_id=data.get('library_id'))
    else:
        settings = Settings()

    mapper = PluginStreamMapper()
    mapper.set_default_values(settings, abspath, probe)

    if mapper.streams_need_processing():
        # Mark this file to be added to the pending tasks
        data['add_file_to_pending_tasks'] = True
        logger.debug("File '{}' should be added to task list. Probe found streams require processing.".format(abspath))
    else:
        logger.debug("File '{}' does not contain streams require processing.".format(abspath))

    return data


def on_worker_process(data):
    """
    Runner function - enables additional configured processing jobs during the worker stages of a task.

    The 'data' object argument includes:
        worker_log              - Array, the log lines that are being tailed by the frontend. Can be left empty.
        library_id              - Number, the library that the current task is associated with.
        exec_command            - Array, a subprocess command that Unmanic should execute. Can be empty.
        command_progress_parser - Function, a function that Unmanic can use to parse the STDOUT of the command to collect progress stats. Can be empty.
        file_in                 - String, the source file to be processed by the command.
        file_out                - String, the destination that the command should output (may be the same as the file_in if necessary).
        original_file_path      - String, the absolute path to the original file.
        repeat                  - Boolean, should this runner be executed again once completed with the same variables.

    :param data:
    :return:
    """

    # Default to no FFMPEG command required. This prevents the FFMPEG command from running if it is not required
    data['exec_command'] = []
    data['repeat'] = False

    # Get the path to the file
    abspath = data.get('file_in')

    # Get file probe
    probe = Probe(logger, allowed_mimetypes=['video'])
    if not probe.file(abspath):
        # File probe failed, skip the rest of this test
        return data

    # Configure settings object (maintain compatibility with v1 plugins)
    if data.get('library_id'):
        settings = Settings(library_id=data.get('library_id'))
    else:
        settings = Settings()

    mapper = PluginStreamMapper()
    mapper.set_default_values(settings, abspath, probe)


    if mapper.streams_need_processing():
        logger.debug("Needs processing")
        mapper.set_output_file(data.get('file_out'))
        mapper.set_ffmpeg_advanced_options('-vf', 'scale={}'.format(mapper.calculate_resolution()))

        # Not quite sure why, cuz I don't really know what PluginStreamMapper "does"..  but if stream_encoding and stream_mapping is set, we wind up
        # not doing anything with the video stream - and only copy the audio stream
        mapper.stream_encoding = ""
        mapper.stream_mapping = ""
        ffmpeg_args = mapper.get_ffmpeg_args()

        logger.debug(ffmpeg_args)

        # Apply ffmpeg args to command
        data['exec_command'] = ['ffmpeg']
        data['exec_command'] += ffmpeg_args

        # Set the parser
        parser = Parser(logger)
        parser.set_probe(probe)
        data['command_progress_parser'] = parser.parse_progress

    return data




class PluginStreamMapper(StreamMapper):
    def __init__(self):
        super(PluginStreamMapper, self).__init__(logger, ['video'])
        self.settings = None

    def set_default_values(self, settings, abspath, probe):
        """
        Configure the stream mapper with defaults

        :param settings:
        :param abspath:
        :param probe:
        :return:
        """
        self.abspath = abspath
        # Set the file probe data
        self.set_probe(probe)
        # Set the input file
        self.set_input_file(abspath)
        # Configure settings
        self.settings = settings

    def calculate_resolution(self):
        force_aspect_ratio = self.settings.get_setting('Force aspect ratio')
        desired_height = int(self.settings.get_setting('Resolution'))
        desired_width = -1
        if (force_aspect_ratio):
            desired_width = int(desired_height * 16 / 9)

        return "{}:{}".format(desired_width,desired_height)


    def test_stream_needs_processing(self, stream_info: dict):
        desired_height = int(self.settings.get_setting('Resolution'))

        logger.debug("Stream height: {} Desired height: {}".format(stream_info['height'], desired_height))
        if (stream_info['height'] > desired_height):
            return True

        return False

    def custom_stream_mapping(self, stream_info: dict, stream_id: int):
        return {
            'stream_mapping': [],
            'stream_encoding': [],
        }
