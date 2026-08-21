import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/widgets/fin_integration_cards.dart';

/// Section divider used to group settings rows under a labelled heading.
///
/// Renders a short primary-colour accent bar followed by an uppercase-weight
/// label. Shared by any settings content panel that groups its rows into
/// sections (Directories, Secondary).
class SettingsSectionHeader extends StatelessWidget {
  /// Heading text shown beside the accent bar.
  final String label;

  const SettingsSectionHeader({super.key, required this.label});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isRomDirectoriesHeader =
        label == AppLocale.romDirectories.getString(context);

    final header = Padding(
      padding: EdgeInsets.only(bottom: 8.r, top: 4.r, left: 2.r),
      child: Row(
        children: [
          Container(
            width: 3.r,
            height: 14.r,
            decoration: BoxDecoration(
              color: theme.colorScheme.primary,
              borderRadius: BorderRadius.circular(2.r),
            ),
          ),
          SizedBox(width: 8.r),
          Text(
            label,
            style: TextStyle(
              fontSize: 11.r,
              fontWeight: FontWeight.bold,
              color: theme.colorScheme.primary,
              letterSpacing: 0.5,
            ),
          ),
        ],
      ),
    );

    // The Directories screen already places all iOS emulator integration
    // cards immediately before its ROM Directories section. Inject Fin here
    // so it lives in the same scrollable group without coupling the shared
    // Directories controller to Fin-specific state/actions.
    if (Platform.isIOS && isRomDirectoriesHeader) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [const FinIntegrationCards(), header],
      );
    }

    return header;
  }
}
