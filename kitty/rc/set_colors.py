#!/usr/bin/env python
# License: GPLv3 Copyright: 2020, Kovid Goyal <kovid at kovidgoyal.net>


import os
from typing import TYPE_CHECKING, Dict, Iterable, Optional

from kitty.cli import emph
from kitty.config import parse_config
from kitty.fast_data_types import Color, patch_color_profiles

from .base import (
    MATCH_TAB_OPTION,
    MATCH_WINDOW_OPTION,
    ArgsType,
    Boss,
    ParsingOfArgsFailed,
    PayloadGetType,
    PayloadType,
    RCOptions,
    RemoteCommand,
    ResponseType,
    Window,
)

if TYPE_CHECKING:
    from kitty.cli_stub import SetColorsRCOptions as CLIOptions


def parse_colors(args: Iterable[str]) -> Dict[str, Optional[int]]:
    from kitty.options.types import nullable_colors
    colors: Dict[str, Optional[Color]] = {}
    nullable_color_map: Dict[str, Optional[int]] = {}
    for spec in args:
        if '=' in spec:
            colors.update(parse_config((spec.replace('=', ' '),)))
        else:
            with open(os.path.expanduser(spec), encoding='utf-8', errors='replace') as f:
                colors.update(parse_config(f))
    for k in nullable_colors:
        q = colors.pop(k, False)
        if q is not False:
            val = int(q) if isinstance(q, Color) else None
            nullable_color_map[k] = val
    ans: Dict[str, Optional[int]] = {k: int(v) for k, v in colors.items() if isinstance(v, Color)}
    ans.update(nullable_color_map)
    return ans


class SetColors(RemoteCommand):

    protocol_spec = __doc__ = '''
    colors+/dict.colors: An object mapping names to colors as 24-bit RGB integers or null for nullable colors
    match_window/str: Window to change colors in
    match_tab/str: Tab to change colors in
    all/bool: Boolean indicating change colors everywhere or not
    configured/bool: Boolean indicating whether to change the configured colors. Must be True if reset is True
    reset/bool: Boolean indicating colors should be reset to startup values
    '''

    short_desc = 'Set terminal colors'
    desc = (
        'Set the terminal colors for the specified windows/tabs (defaults to active window).'
        ' You can either specify the path to a conf file'
        ' (in the same format as :file:`kitty.conf`) to read the colors from or you can specify individual colors,'
        ' for example::\n\n'
        '    kitten @ set-colors foreground=red background=white'
    )
    options_spec = '''\
--all -a
type=bool-set
By default, colors are only changed for the currently active window. This option will
cause colors to be changed in all windows.


--configured -c
type=bool-set
Also change the configured colors (i.e. the colors kitty will use for new
windows or after a reset).


--reset
type=bool-set
Restore all colors to the values they had at kitty startup. Note that if you specify
this option, any color arguments are ignored and :option:`kitten @ set-colors --configured` and :option:`kitten @ set-colors --all` are implied.
''' + '\n\n' + MATCH_WINDOW_OPTION + '\n\n' + MATCH_TAB_OPTION.replace('--match -m', '--match-tab -t')
    args = RemoteCommand.Args(spec='COLOR_OR_FILE ...', json_field='colors', special_parse='parse_colors_and_files(args)',
                              completion=RemoteCommand.CompletionSpec.from_string('type:file group:"CONF files", ext:conf'))

    def message_to_kitty(self, global_opts: RCOptions, opts: 'CLIOptions', args: ArgsType) -> PayloadType:
        final_colors: Dict[str, Optional[int]] = {}
        if not opts.reset:
            try:
                final_colors = parse_colors(args)
            except FileNotFoundError as err:
                raise ParsingOfArgsFailed(f'The colors configuration file {emph(err.filename)} was not found.') from err
            except Exception as err:
                raise ParsingOfArgsFailed(str(err)) from err
        ans = {
            'match_window': opts.match, 'match_tab': opts.match_tab,
            'all': opts.all or opts.reset, 'configured': opts.configured or opts.reset,
            'colors': final_colors, 'reset': opts.reset,
        }
        return ans

    def response_from_kitty(self, boss: Boss, window: Optional[Window], payload_get: PayloadGetType) -> ResponseType:
        windows = self.windows_for_payload(boss, window, payload_get)
        colors: Dict[str, Optional[int]] = payload_get('colors')
        if payload_get('reset'):
            colors = {k: None if v is None else int(v) for k, v in boss.color_settings_at_startup.items()}
        profiles = tuple(w.screen.color_profile for w in windows if w)
        patch_color_profiles(colors, profiles, payload_get('configured'))
        boss.patch_colors(colors, payload_get('configured'))
        default_bg_changed = 'background' in colors
        for w in windows:
            if w:
                if default_bg_changed:
                    boss.default_bg_changed_for(w.id)
                w.refresh()
        return None


set_colors = SetColors()
