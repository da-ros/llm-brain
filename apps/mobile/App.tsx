import {useEffect, useMemo} from 'react';
import {useColorScheme, View} from 'react-native';
import {NavigationContainer} from '@react-navigation/native';
import {createNativeStackNavigator} from '@react-navigation/native-stack';
import {SafeAreaProvider} from 'react-native-safe-area-context';

import {createBrain, type Brain} from './src/brain';
import {AboutScreen, HelpScreen, SettingsScreen} from './src/screens/SettingsScreen';
import {AuthScreen} from './src/screens/AuthScreen';
import {ChatScreen} from './src/screens/ChatScreen';
import {CompareScreen} from './src/screens/CompareScreen';
import {StatusScreen} from './src/screens/StatusScreen';
import {dark, light} from './src/theme';
import {BrainContext, ThemeContext, useBrain, useSnapshot} from './src/ui';

const Stack = createNativeStackNavigator();

function Gate() {
  const brain = useBrain();
  const snapshot = useSnapshot(brain);
  const scheme = useColorScheme();
  const palette = useMemo(() => {
    const mode = snapshot.theme === 'system' ? scheme : snapshot.theme;
    return mode === 'dark' ? dark : light;
  }, [scheme, snapshot.theme]);

  if (!snapshot.ready) {
    return <View style={{flex: 1, backgroundColor: light.bg}} />;
  }

  return (
    <ThemeContext.Provider value={palette}>
      {snapshot.token ? (
        <Stack.Navigator initialRouteName="Chat" screenOptions={{headerShown: false, contentStyle: {backgroundColor: palette.bg}}}>
          <Stack.Screen name="Chat" component={ChatScreen} />
          <Stack.Screen name="Status" component={StatusScreen} />
          <Stack.Screen name="Compare" component={CompareScreen} />
          <Stack.Screen name="Settings" component={SettingsScreen} />
          <Stack.Screen name="Help" component={HelpScreen} />
          <Stack.Screen name="About" component={AboutScreen} />
        </Stack.Navigator>
      ) : (
        <Stack.Navigator screenOptions={{headerShown: false, contentStyle: {backgroundColor: palette.bg}}}>
          <Stack.Screen name="Auth" component={AuthScreen} />
        </Stack.Navigator>
      )}
    </ThemeContext.Provider>
  );
}

export default function App({brain}: {brain?: Brain}) {
  const instance = useMemo(() => brain ?? createBrain(), [brain]);
  useEffect(() => {
    void instance.boot();
  }, [instance]);
  return (
    <BrainContext.Provider value={instance}>
      <SafeAreaProvider>
        <NavigationContainer>
          <Gate />
        </NavigationContainer>
      </SafeAreaProvider>
    </BrainContext.Provider>
  );
}
