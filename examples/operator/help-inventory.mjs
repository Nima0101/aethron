import ts from '../clients/typescript/node_modules/typescript/lib/typescript.js';
import {createHash} from 'node:crypto';

const invalid=()=>{throw new Error('unsupported_help_source');};
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const equal=(a,b)=>JSON.stringify([...a].sort())===JSON.stringify([...b].sort());
function parse(text,name) {
  if(typeof text!=='string')invalid();
  const tree=ts.createSourceFile(name+'.ts',text,ts.ScriptTarget.Latest,true,ts.ScriptKind.TS);
  if(tree.parseDiagnostics.length)invalid();
  return tree;
}
function union(tree,name) {
  const matches=tree.statements.filter(n=>ts.isTypeAliasDeclaration(n)&&n.name.text===name);
  if(matches.length!==1||!ts.isUnionTypeNode(matches[0].type))invalid();
  const values=matches[0].type.types.map(n=>{
    if(!ts.isLiteralTypeNode(n)||!ts.isStringLiteral(n.literal))invalid();
    return n.literal.text;
  });
  if(new Set(values).size!==values.length)invalid();
  return values;
}
function literal(node) {
  if(!node)invalid();
  if(ts.isAsExpression(node)||ts.isParenthesizedExpression(node))return literal(node.expression);
  if(ts.isStringLiteral(node)) {if(!node.text.trim())invalid();return node.text;}
  if(ts.isArrayLiteralExpression(node))return node.elements.map(literal);
  if(ts.isObjectLiteralExpression(node)) {
    const entries=node.properties.map(p=>{
      if(!ts.isPropertyAssignment(p)||(!ts.isIdentifier(p.name)&&!ts.isStringLiteral(p.name)))invalid();
      return [p.name.text,literal(p.initializer)];
    });
    if(new Set(entries.map(([key])=>key)).size!==entries.length)invalid();
    return Object.fromEntries(entries);
  }
  invalid(); // Never evaluate expressions or execute source to discover help.
}
function dictionary(tree,name) {
  const declarations=tree.statements.filter(ts.isVariableStatement).flatMap(n=>[...n.declarationList.declarations]);
  const matches=declarations.filter(n=>ts.isIdentifier(n.name)&&n.name.text===name);
  if(matches.length!==1)invalid();
  const value=literal(matches[0].initializer);
  if(!value||Array.isArray(value)||typeof value!=='object')invalid();
  return value;
}

/** Build-time extraction only, not a general TypeScript evaluator or complete
 * product help audit. The browser artifact is separately exercised against this
 * inventory. The build caller must obtain revision status from its own checkout. */
export function createStateHelpInventory(sources,moduleBytes,revision) {
  if(!revision||!equal(Object.keys(revision),['head','modified'])||
     typeof revision.head!=='string'||!/^[0-9a-f]{40}$/.test(revision.head)||typeof revision.modified!=='boolean') {
    throw new Error('invalid_help_revision');
  }
  if(!sources||!equal(Object.keys(sources),['presenter','connection']))invalid();
  const presenter=parse(sources.presenter,'presenter'),connection=parse(sources.connection,'connection');
  const locales=union(presenter,'Locale');
  if(!equal(locales,['en','sv-SE']))invalid();
  const topics=[];
  for(const [tree,type,variable,prefix,labels] of [
    [presenter,'PresentationState','guidance','observation',[]],
    [connection,'State','copy','connection',['title','start','stop','help']],
  ]) {
    const states=union(tree,type),copy=dictionary(tree,variable);
    if(!equal(Object.keys(copy),locales))invalid();
    for(const locale of locales) {
      if(!copy[locale]||Array.isArray(copy[locale])||typeof copy[locale]!=='object'||
         !equal(Object.keys(copy[locale]),[...states,...labels]))invalid();
      if(labels.some(key=>typeof copy[locale][key]!=='string'))invalid();
    }
    for(const state of states) {
      if(!/^[a-z][a-z_]*$/.test(state))invalid();
      const translations=Object.fromEntries(locales.map(locale=>{
        const entry=copy[locale][state];
        if(!Array.isArray(entry)||entry.length!==2||entry.some(v=>typeof v!=='string'||!v.trim()))invalid();
        return [locale,{title:entry[0],body:entry[1]}];
      }));
      topics.push({id:`${prefix}.${state}`,owner:'P12',status:'component-only',access:'public-state-guidance',translations});
    }
  }
  return {format:'aethron-state-help-v1',ui_schema:'aethron-observation-component-v1',api_schema:'aethron-edge-v1',
    source_revision:revision.head,source_modified:revision.modified,release_sha:revision.modified?null:revision.head,
    product_help_complete:false,coverage_scope:'observation-and-connection-state-guidance',
    remaining_coverage:['action-specific topics','routes and role/permission inventory','search and onboarding','manuals and installed-product acceptance'],
    locales,source_sha256:Object.fromEntries(Object.entries(sources).map(([name,text])=>[name,hash(text)])),
    module_sha256:hash(moduleBytes),topics:topics.sort((a,b)=>a.id<b.id?-1:a.id>b.id?1:0)};
}

/** Separate versioned inventory for the four shipped button actions. */
export function createActionHelpInventory(source,moduleBytes,revision) {
  if(!revision||!equal(Object.keys(revision),['head','modified'])||
     typeof revision.head!=='string'||!/^[0-9a-f]{40}$/.test(revision.head)||typeof revision.modified!=='boolean') {
    throw new Error('invalid_help_revision');
  }
  const tree=parse(source,'action-help'),actions=union(tree,'Action'),copy=dictionary(tree,'actionGuidance');
  const locales=['en','sv-SE'];
  if(!equal(Object.keys(copy),locales))invalid();
  for(const locale of locales) {
    if(!copy[locale]||Array.isArray(copy[locale])||typeof copy[locale]!=='object'||!equal(Object.keys(copy[locale]),actions))invalid();
  }
  const topics=actions.sort().map(id=>{
    if(!/^[a-z]+\.[a-zA-Z-]+$/.test(id))invalid();
    const translations=Object.fromEntries(locales.map(locale=>{
      const pair=copy[locale][id];
      if(!Array.isArray(pair)||pair.length!==2||pair.some(text=>typeof text!=='string'))invalid();
      return [locale,{title:pair[0],body:pair[1]}];
    }));
    return {id,owner:'P12',status:'component-only',access:'public-action-guidance',translations};
  });
  return {format:'aethron-action-help-v1',ui_schema:'aethron-observation-component-v1',api_schema:'aethron-edge-v1',
    source_revision:revision.head,source_modified:revision.modified,release_sha:revision.modified?null:revision.head,
    product_help_complete:false,coverage_scope:'four-observation-client-buttons',locales,
    remaining_coverage:['routes and role/permission inventory','search and onboarding','manuals and installed-product acceptance'],
    source_sha256:{'action-help':hash(source)},module_sha256:hash(moduleBytes),topics};
}
