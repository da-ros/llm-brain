/**
 * React Native 0.81 codegen only accepts React.ElementRef.
 * react-native-screens types the same slot as React.ComponentRef.
 * Accept both so `pod install` can generate the native specs.
 */
const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');
const files = [
  'node_modules/@react-native/codegen/lib/parsers/typescript/components/commands.js',
  'node_modules/@react-native/codegen/lib/parsers/flow/components/commands.js',
];

for (const rel of files) {
  const file = path.join(root, rel);
  if (!fs.existsSync(file)) {
    continue;
  }
  const text = fs.readFileSync(file, 'utf8');
  if (text.includes("'ComponentRef'")) {
    continue;
  }
  const next = text
    .replace(
      ": _firstParam$typeAnnot2.name) === 'ElementRef'",
      ": _firstParam$typeAnnot2.name) === 'ElementRef' ||\n      ((_firstParam$typeAnnot2 = firstParam.typeAnnotation.typeName.right) ===\n        null || _firstParam$typeAnnot2 === void 0\n        ? void 0\n        : _firstParam$typeAnnot2.name) === 'ComponentRef')",
    )
    .replace(
      "firstParam.id.id.name === 'ElementRef'",
      "(firstParam.id.id.name === 'ElementRef' || firstParam.id.id.name === 'ComponentRef')",
    )
    .replace(
      'must be of type React.ElementRef<>',
      'must be of type React.ElementRef<> or React.ComponentRef<>',
    );
  if (next === text) {
    throw new Error(`Could not patch ${rel}`);
  }
  // The TypeScript check is a chain of &&. Parenthesize the || so it stays inside that chain.
  const wrapped = next.replace(
    "=== 'React' &&\n      ((_firstParam$typeAnnot2 = firstParam.typeAnnotation.typeName.right) ===",
    "=== 'React' &&\n      (((_firstParam$typeAnnot2 = firstParam.typeAnnotation.typeName.right) ===",
  );
  fs.writeFileSync(file, wrapped);
  console.log(`patched ${rel}`);
}
