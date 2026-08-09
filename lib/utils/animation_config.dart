import 'package:flutter/material.dart';

/// Centralized configuration for animation durations and curves.
class AnimationConfig {
  /// Standard duration for fast scroll animations.
  static const Duration scrollFast = Duration(milliseconds: 640);

  /// Standard duration for normal scroll animations.
  static const Duration scrollNormal = Duration(milliseconds: 640);

  /// Duration for scaling effects on UI cards.
  static const Duration scaleCard = Duration(milliseconds: 512);

  /// Duration for scaling effects on game thumbnails/previews.
  static const Duration scaleGame = Duration(milliseconds: 512);

  /// Duration for marquee text scroll cycles.
  static const Duration textScrollDuration = Duration(seconds: 2);

  /// Delay before a text scroll animation begins.
  static const Duration textScrollDelay = Duration(milliseconds: 512);

  /// Preferred curve for smooth UI transitions.
  static Curve get smoothCurve => Curves.fastOutSlowIn;

  /// Preferred curve for rapid UI transitions.
  static Curve get fastCurve => Curves.fastOutSlowIn;

  /// Global factor used to scale all animation durations.
  static const double animationSpeedFactor = 0.5;

  /// Applies the [animationSpeedFactor] to a given [duration].
  static Duration applySpeedFactor(Duration duration) {
    return Duration(
      milliseconds: (duration.inMilliseconds * animationSpeedFactor).round(),
    );
  }
}
