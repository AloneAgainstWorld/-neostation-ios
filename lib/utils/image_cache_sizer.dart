import 'package:flutter/material.dart';

class ImageCacheSizer {
  const ImageCacheSizer._();

  static ImageCacheSizer of(BuildContext context) => ImageCacheSizer._();

  int box2dCacheWidth({
    required int columns,
    double availableWidth = 0,
    double devicePixelRatio = 1.0,
  }) {
    final cv = _cardViewportWidth(columns, availableWidth);
    return (cv * 1.5 * devicePixelRatio).round();
  }

  int systemBgCacheWidth({
    required int columns,
    double availableWidth = 0,
    double devicePixelRatio = 1.0,
  }) {
    final cv = _cardViewportWidth(columns, availableWidth);
    return (cv * devicePixelRatio).round();
  }

  int systemLogoCachedWidth({double devicePixelRatio = 1.0}) {
    return (512 * devicePixelRatio).round();
  }

  int gameWheelCachedWidth({double devicePixelRatio = 1.0}) {
    return (256 * devicePixelRatio).round();
  }

  double _cardViewportWidth(int columns, double availableWidth) {
    if (columns <= 0) return 100;
    final w = availableWidth > 0 ? availableWidth : 640;
    return w / columns;
  }

  // Game grid styled layout (similar to box2d but using LayoutBuilder width)
  int gameGridCacheWidth({
    required int columns,
    required double availableWidth,
    double devicePixelRatio = 1.0,
  }) {
    final spacing = availableWidth * 0.022;
    final totalWidth = availableWidth - 16;
    final cardW = (totalWidth - (columns - 1) * spacing) / columns;
    return (cardW * 1.5 * devicePixelRatio).round();
  }

  int systemCardCacheWidth({
    required int columns,
    required double availableWidth,
    double devicePixelRatio = 1.0,
  }) {
    final spacing = 6.0;
    final totalSpacing = spacing * (columns - 1);
    final cardW = (availableWidth - totalSpacing) / columns;
    return (cardW * devicePixelRatio).round();
  }
}
