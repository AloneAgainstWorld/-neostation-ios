import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

/// Lightweight frosted-glass surface for NeoStation's floating UI.
///
/// Uses a single clipped [BackdropFilter] blur plus a translucent tint and a
/// canvas-painted specular rim. It deliberately avoids refraction/distortion
/// shaders so the effect remains suitable for game browsing screens where the
/// fanart behind the UI may change frequently.
class NeoGlass extends StatelessWidget {
  const NeoGlass({
    super.key,
    required this.child,
    this.cornerRadius = 14,
    this.blur = 3,
    this.tint,
    this.padding,
    this.rimIntensity = 0.5,
  });

  final Widget child;
  final double cornerRadius;
  final double blur;
  final Color? tint;
  final EdgeInsetsGeometry? padding;
  final double rimIntensity;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    // More transparent than the upstream 0.80 default: the private iOS build
    // is designed around landscape fanart and benefits from letting more of it
    // remain visible through the menus.
    final glassTint =
        tint ?? theme.scaffoldBackgroundColor.withValues(alpha: 0.56);
    final borderRadius = BorderRadius.circular(cornerRadius);

    Widget surface = ColoredBox(
      color: glassTint,
      child: padding != null ? Padding(padding: padding!, child: child) : child,
    );

    if (blur > 0) {
      surface = BackdropFilter(
        filter: ui.ImageFilter.blur(sigmaX: blur, sigmaY: blur),
        child: surface,
      );
    }

    return Stack(
      clipBehavior: Clip.none,
      children: [
        ClipRRect(borderRadius: borderRadius, child: surface),
        Positioned.fill(
          child: IgnorePointer(
            child: CustomPaint(
              painter: _GlassRimPainter(
                cornerRadius: cornerRadius,
                intensity: rimIntensity,
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _GlassRimPainter extends CustomPainter {
  const _GlassRimPainter({required this.cornerRadius, required this.intensity});

  final double cornerRadius;
  final double intensity;

  @override
  void paint(Canvas canvas, Size size) {
    if (intensity <= 0 || size.isEmpty) return;

    Path outsetOutline(double strokeWidth) {
      final extent = strokeWidth / 2;
      final rect = (Offset.zero & size).inflate(extent);
      return Path()
        ..addRRect(
          RRect.fromRectAndRadius(
            rect,
            Radius.circular(cornerRadius + extent),
          ),
        );
    }

    final bounds = Offset.zero & size;
    final light = Alignment.topLeft;
    final sweep = LinearGradient(
      begin: light,
      end: Alignment.bottomRight,
      colors: [
        Colors.white.withValues(alpha: 0.60 * intensity),
        Colors.white.withValues(alpha: 0.40 * intensity),
        Colors.white.withValues(alpha: 0.20 * intensity),
        Colors.white.withValues(alpha: 0.35 * intensity),
      ],
      stops: const [0.0, 0.3, 0.6, 0.9],
    ).createShader(bounds);

    canvas.drawPath(
      outsetOutline(1.2.h),
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.2.h
        ..isAntiAlias = true
        ..blendMode = BlendMode.overlay
        ..shader = sweep,
    );

    canvas.drawPath(
      outsetOutline(0.9.h),
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 0.9.h
        ..isAntiAlias = true
        ..blendMode = BlendMode.overlay
        ..shader = LinearGradient(
          begin: light,
          end: Alignment.bottomRight,
          colors: [
            Colors.white.withValues(alpha: 0.70 * intensity),
            Colors.white.withValues(alpha: 0.35 * intensity),
            Colors.white.withValues(alpha: 0.20 * intensity),
          ],
          stops: const [0.0, 0.5, 1.0],
        ).createShader(bounds),
    );
  }

  @override
  bool shouldRepaint(_GlassRimPainter oldDelegate) =>
      oldDelegate.cornerRadius != cornerRadius ||
      oldDelegate.intensity != intensity;
}
