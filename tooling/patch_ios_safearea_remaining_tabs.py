from pathlib import Path

RA = Path('lib/screens/retro_achievements_screen/ra_content.dart')
SEARCH = Path('lib/screens/search_screen/search_screen.dart')
NEOSYNC = Path('lib/screens/neo_sync_screen/login_screen/neo_sync_content.dart')
SYSTEMS = Path('lib/screens/systems_screen/system_content.dart')

ra = RA.read_text(encoding='utf-8')
search = SEARCH.read_text(encoding='utf-8')
neosync = NEOSYNC.read_text(encoding='utf-8')
systems = SYSTEMS.read_text(encoding='utf-8')


def rep(text, old, new, label):
    if old not in text:
        raise SystemExit(f'anchor not found: {label}')
    return text.replace(old, new, 1)

# RetroAchievements: protect both login and connected dashboard content.
ra = rep(
    ra,
    "import 'package:flutter/material.dart';\n",
    "import 'package:flutter/foundation.dart';\nimport 'package:flutter/material.dart';\n",
    'RA foundation import',
)
ra = rep(
    ra,
    """    final keyboardInset = MediaQuery.viewInsetsOf(context).bottom;\n\n    return Padding(\n      padding: EdgeInsets.symmetric(horizontal: 12.r),""",
    """    final keyboardInset = MediaQuery.viewInsetsOf(context).bottom;\n    final safePadding = MediaQuery.viewPaddingOf(context);\n    final isIOS = defaultTargetPlatform == TargetPlatform.iOS;\n    final safeLeft = isIOS ? safePadding.left : 0.0;\n    final safeRight = isIOS ? safePadding.right : 0.0;\n\n    return Padding(\n      padding: EdgeInsets.fromLTRB(12.r + safeLeft, 0, 12.r + safeRight, 0),""",
    'RA landscape padding',
)

# Standard game search: keep the search field, result list and filters clear.
search = rep(
    search,
    """  Widget build(BuildContext context) {\n    final theme = Theme.of(context);\n    // Tab content sits under the global header,""",
    """  Widget build(BuildContext context) {\n    final theme = Theme.of(context);\n    final safePadding = MediaQuery.viewPaddingOf(context);\n    final safeLeft = Platform.isIOS ? safePadding.left : 0.0;\n    final safeRight = Platform.isIOS ? safePadding.right : 0.0;\n    // Tab content sits under the global header,""",
    'search safe vars',
)
search = rep(
    search,
    "padding: EdgeInsets.symmetric(horizontal: 12.r),",
    "padding: EdgeInsets.fromLTRB(12.r + safeLeft, 0, 12.r + safeRight, 0),",
    'search horizontal padding',
)

# NeoSync: protect both logged-out auth UI and logged-in cloud dashboard.
neosync = rep(
    neosync,
    """      builder: (context, authService, child) {\n        // Load initial data when user logs in (only once per app session)""",
    """      builder: (context, authService, child) {\n        final safePadding = MediaQuery.viewPaddingOf(context);\n        final safeLeft = Platform.isIOS ? safePadding.left : 0.0;\n        final safeRight = Platform.isIOS ? safePadding.right : 0.0;\n        // Load initial data when user logs in (only once per app session)""",
    'NeoSync auth safe vars',
)
neosync = rep(
    neosync,
    "padding: EdgeInsets.symmetric(horizontal: 16.r),",
    "padding: EdgeInsets.fromLTRB(16.r + safeLeft, 0, 16.r + safeRight, 0),",
    'NeoSync logged-out padding',
)
neosync = rep(
    neosync,
    """    return LayoutBuilder(\n      builder: (context, constraints) {\n        return Padding(\n          padding: EdgeInsets.only(\n            top: 52.r,\n            left: 8.r,\n            right: 8.r,""",
    """    return LayoutBuilder(\n      builder: (context, constraints) {\n        final safePadding = MediaQuery.viewPaddingOf(context);\n        final safeLeft = Platform.isIOS ? safePadding.left : 0.0;\n        final safeRight = Platform.isIOS ? safePadding.right : 0.0;\n        return Padding(\n          padding: EdgeInsets.only(\n            top: 52.r,\n            left: 8.r + safeLeft,\n            right: 8.r + safeRight,""",
    'NeoSync logged-in padding',
)

# Main Systems menu: protect console cards/content while leaving the global header untouched.
systems = rep(
    systems,
    "import 'package:flutter/material.dart';\n",
    "import 'package:flutter/foundation.dart';\nimport 'package:flutter/material.dart';\n",
    'systems foundation import',
)
systems = rep(
    systems,
    """        final routeIsCurrent = ModalRoute.of(context)?.isCurrent ?? true;\n        _syncHomeMusic(showContent && routeIsCurrent);\n\n        final Widget phase;""",
    """        final routeIsCurrent = ModalRoute.of(context)?.isCurrent ?? true;\n        _syncHomeMusic(showContent && routeIsCurrent);\n        final safePadding = MediaQuery.viewPaddingOf(context);\n        final isIOS = defaultTargetPlatform == TargetPlatform.iOS;\n        final safeLeft = isIOS ? safePadding.left : 0.0;\n        final safeRight = isIOS ? safePadding.right : 0.0;\n\n        final Widget phase;""",
    'systems safe vars',
)
systems = rep(
    systems,
    """        if (showContent) return content;\n        return ColoredBox(""",
    """        if (showContent) {\n          return Padding(\n            padding: EdgeInsets.only(left: safeLeft, right: safeRight),\n            child: content,\n          );\n        }\n        return ColoredBox(""",
    'systems content safe padding',
)

RA.write_text(ra, encoding='utf-8')
SEARCH.write_text(search, encoding='utf-8')
NEOSYNC.write_text(neosync, encoding='utf-8')
SYSTEMS.write_text(systems, encoding='utf-8')
