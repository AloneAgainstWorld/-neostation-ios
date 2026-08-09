import 'package:flutter/material.dart';
import 'package:neostation/services/notification_service.dart';
import 'package:neostation/services/neosync/auth_service.dart';
import 'package:neostation/providers/neo_sync_provider.dart';
import 'package:provider/provider.dart';
import 'package:neostation/services/logger_service.dart';

class NeoSyncControlsWidget extends StatefulWidget {
  const NeoSyncControlsWidget({super.key});

  @override
  NeoSyncControlsWidgetState createState() => NeoSyncControlsWidgetState();
}

class NeoSyncControlsWidgetState extends State<NeoSyncControlsWidget> {
  @override
  void initState() {
    super.initState();
    _connectNotifications();
  }

  static final _log = LoggerService.instance;

  Future<void> _connectNotifications() async {
    final notificationService = Provider.of<NotificationService>(
      context,
      listen: false,
    );
    final authService = Provider.of<AuthService>(context, listen: false);

    // Check whether the user is authenticated
    if (!authService.isLoggedIn) {
      return;
    }

    // Don't await to prevent blocking UI
    notificationService
        .connect()
        .then((_) {
          if (notificationService.isConnected) {
          } else {
            _log.e(
              'Failed to connect to notifications. Error: ${notificationService.lastError}',
            );
          }
        })
        .catchError((error) {
          _log.e('Failed to connect to notifications: $error');
        });
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<NeoSyncProvider>(
      builder: (context, neoSyncProvider, child) {
        // Only show sync status if there's active syncing or recent activity
        if (!neoSyncProvider.isSyncing &&
            neoSyncProvider.processedItems.isEmpty) {
          return SizedBox.shrink(); // Hide widget when no sync activity
        }

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              padding: EdgeInsets.all(10.0),
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.surface,
                borderRadius: BorderRadius.circular(6.0),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (neoSyncProvider.isSyncing) ...[
                    Text(
                      neoSyncProvider.syncStatus,
                      style: TextStyle(fontSize: 11.0),
                    ),
                    SizedBox(height: 6.0),
                    LinearProgressIndicator(
                      value: neoSyncProvider.syncProgress,
                      minHeight: 3.0,
                    ),
                    SizedBox(height: 6.0),
                  ],

                  // Last sync statistics
                  if (neoSyncProvider.uploadedFiles > 0 ||
                      neoSyncProvider.downloadedFiles > 0 ||
                      neoSyncProvider.skippedFiles > 0)
                    Wrap(
                      spacing: 8.0,
                      runSpacing: 4.0,
                      children: [
                        if (neoSyncProvider.uploadedFiles > 0)
                          _buildStatChip(
                            '↑ ${neoSyncProvider.uploadedFiles}',
                            'Up',
                            Colors.green,
                          ),
                        if (neoSyncProvider.downloadedFiles > 0)
                          _buildStatChip(
                            '↓ ${neoSyncProvider.downloadedFiles}',
                            'Down',
                            Colors.blue,
                          ),
                        if (neoSyncProvider.skippedFiles > 0)
                          _buildStatChip(
                            '✓ ${neoSyncProvider.skippedFiles}',
                            'Skip',
                            Colors.grey,
                          ),
                      ],
                    ),
                ],
              ),
            ),
          ],
        );
      },
    );
  }

  Widget _buildStatChip(String value, String label, Color color) {
    return Container(
      padding: EdgeInsets.symmetric(horizontal: 6.0, vertical: 2.0),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(8.0),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            value,
            style: TextStyle(
              fontSize: 9.0,
              fontWeight: FontWeight.bold,
              color: color,
            ),
          ),
          SizedBox(width: 3.0),
          Text(label, style: TextStyle(fontSize: 8.0, color: color)),
        ],
      ),
    );
  }
}
