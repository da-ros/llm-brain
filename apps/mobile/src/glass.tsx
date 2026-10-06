import {StyleSheet, View, type StyleProp, type ViewStyle} from 'react-native';
import {BlurView} from '@react-native-community/blur';

import {useTheme} from './context';
import type {ReactNode} from 'react';

/**
 * A translucent surface in the shape of iOS liquid glass: a blur of whatever
 * sits behind it, a soft tint on top, and a bright hairline edge.
 *
 * `style` positions the surface, `contentStyle` carries the padding, and
 * `surfaceStyle` tweaks the glass itself. Padding cannot go on the surface:
 * the blur layers fill it, and padding would push them inward. The shadow
 * sits on an outer view because the surface clips, and a clipped shadow is
 * invisible. `fill` stretches the surface when the parent sets the height.
 */
export function Glass({
  children,
  style,
  contentStyle,
  surfaceStyle,
  radius = 24,
  strong,
  floating,
  fill,
}: {
  children?: ReactNode;
  style?: StyleProp<ViewStyle>;
  contentStyle?: StyleProp<ViewStyle>;
  surfaceStyle?: StyleProp<ViewStyle>;
  radius?: number;
  strong?: boolean;
  floating?: boolean;
  fill?: boolean;
}) {
  const theme = useTheme();
  return (
    <View style={[floating && styles.floating, floating && {shadowColor: theme.glassShadow}, style]}>
      <View
        style={[
          styles.surface,
          fill && styles.fill,
          {borderRadius: radius, borderColor: theme.glassBorder},
          surfaceStyle,
        ]}>
        <BlurView
          style={StyleSheet.absoluteFill}
          blurType={theme.blur}
          blurAmount={strong ? 26 : 16}
          reducedTransparencyFallbackColor={theme.card}
        />
        <View style={[StyleSheet.absoluteFill, {backgroundColor: strong ? theme.glassStrong : theme.glass}]} />
        <View style={[fill && styles.fill, contentStyle]}>{children}</View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  surface: {borderWidth: StyleSheet.hairlineWidth * 2, overflow: 'hidden', backgroundColor: 'transparent'},
  fill: {flex: 1},
  floating: {shadowOpacity: 0.14, shadowRadius: 16, shadowOffset: {width: 0, height: 8}, elevation: 8},
});
