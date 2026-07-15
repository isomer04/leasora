#!/usr/bin/env node
/**
 * Generate TypeScript types from FastAPI OpenAPI schema
 * 
 * Usage:
 *   node scripts/generate-types.js [--api-url <url>]
 * 
 * Defaults:
 *   API URL: http://localhost:8000
 */

const fs = require('fs');
const path = require('path');
const https = require('https');
const http = require('http');

// Configuration
const API_URL = process.argv.includes('--api-url')
  ? process.argv[process.argv.indexOf('--api-url') + 1]
  : 'http://localhost:8000';

const OPENAPI_ENDPOINT = `${API_URL}/openapi.json`;
const OUTPUT_DIR = path.join(__dirname, '..', 'packages', 'shared-types', 'src');
const OUTPUT_FILE = path.join(OUTPUT_DIR, 'api.ts');

console.log('🔄 Generating TypeScript types from OpenAPI schema...');
console.log(`📍 API URL: ${API_URL}`);
console.log(`📁 Output: ${OUTPUT_FILE}`);

// Ensure output directory exists
if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

// Fetch OpenAPI schema
function fetchOpenAPI() {
  return new Promise((resolve, reject) => {
    console.log(`📥 Fetching ${OPENAPI_ENDPOINT}...`);
    
    const protocol = OPENAPI_ENDPOINT.startsWith('https') ? https : http;
    const url = new URL(OPENAPI_ENDPOINT);
    
    const request = protocol.get(
      {
        hostname: url.hostname,
        port: url.port,
        path: url.pathname + url.search,
        protocol: url.protocol,
      },
      (res) => {
        if (res.statusCode !== 200) {
          reject(new Error(`Failed to fetch OpenAPI schema: HTTP ${res.statusCode}`));
          return;
        }
        
        let data = '';
        res.on('data', chunk => (data += chunk));
        res.on('end', () => {
          try {
            const schema = JSON.parse(data);
            resolve(schema);
          } catch (e) {
            reject(new Error(`Invalid JSON in OpenAPI response: ${e.message}`));
          }
        });
      }
    );
    
    request.on('error', reject);
    request.setTimeout(10000, () => {
      request.destroy();
      reject(new Error('Request timeout'));
    });
  });
}

// Generate TypeScript types from OpenAPI schema
function generateTypes(schema) {
  console.log('✨ Generating TypeScript code...');
  
  const types = [];
  
  // Add header comment
  types.push('/**');
  types.push(' * Auto-generated TypeScript types from FastAPI OpenAPI schema');
  types.push(' *');
  types.push(' * DO NOT EDIT MANUALLY - regenerate with: pnpm gen:types');
  types.push(' */');
  types.push('');
  
  // Extract and generate types for each schema
  if (schema.components && schema.components.schemas) {
    for (const [name, schemaObj] of Object.entries(schema.components.schemas)) {
      // Enum schemas (e.g. pydantic's `class SignalLabel(str, Enum)`) have no
      // `properties` — they're a plain string union, not an object shape.
      // Emitting `export interface Foo {}` for these is both wrong (empty
      // object type, not the actual union) and the reason every field that
      // referenced them fell back to `any`.
      if (Array.isArray(schemaObj.enum)) {
        types.push(`export type ${name} = ${enumLiteralUnion(schemaObj)};`);
        types.push('');
        continue;
      }

      types.push(`export interface ${name} {`);

      if (schemaObj.properties) {
        for (const [propName, propSchema] of Object.entries(schemaObj.properties)) {
          const required = schemaObj.required && schemaObj.required.includes(propName);
          const optional = required ? '' : '?';
          const typeStr = getTypeString(propSchema);
          const description = propSchema.description ? ` // ${propSchema.description}` : '';
          types.push(`  ${propName}${optional}: ${typeStr};${description}`);
        }
      }

      types.push('}');
      types.push('');
    }
  }
  
  // Generate endpoint types
  if (schema.paths) {
    types.push('// API Endpoints');
    types.push('');
    
    for (const [path, methods] of Object.entries(schema.paths)) {
      for (const [method, operation] of Object.entries(methods)) {
        if (!['get', 'post', 'put', 'delete', 'patch'].includes(method.toLowerCase())) {
          continue;
        }
        
        // Sanitize operationId: remove invalid chars from path-based fallback
        const rawOperationId = operation.operationId || `${method}_${path}`;
        const operationId = rawOperationId
          .replace(/[^a-zA-Z0-9_]/g, '_')  // Replace invalid chars with underscore
          .replace(/_+/g, '_')             // Collapse multiple underscores
          .replace(/^_|_$/g, '');          // Trim leading/trailing underscores
        
        const requestBodySchema = operation.requestBody?.content?.['application/json']?.schema;
        const responseSchema = operation.responses?.['200']?.content?.['application/json']?.schema;
        
        if (requestBodySchema && responseSchema) {
          types.push(`// ${operation.summary || operationId}`);
          types.push(`export declare function ${camelize(operationId)}(data: ${getRefName(requestBodySchema)}): Promise<${getRefName(responseSchema)}>;`);
          types.push('');
        }
      }
    }
  }
  
  return types.join('\n');
}

// Build a `'a' | 'b' | 'c'` literal union string for a schema with an `enum`.
function enumLiteralUnion(schema) {
  return schema.enum.map((value) => `'${value}'`).join(' | ');
}

// Determine TypeScript type from JSON schema
function getTypeString(schema) {
  if (schema.$ref) {
    return getRefName(schema);
  }

  // pydantic emits `anyOf: [<real type>, {type: "null"}]` for every
  // `Optional[X]` / `X | None` field instead of a bare nullable type. Without
  // handling this, every such field previously fell through to the `any`
  // default below (e.g. `chunk_count?: any`, `signal?: any`).
  //
  // The `null` member is semantically meaningful, not just a marker for
  // "this field is optional" — FastAPI/pydantic serialize `None` as a JSON
  // `null` on the wire (e.g. `chunk_count: null`), so a field typed
  // `int | None` is BOTH optional (may be absent, handled by the `?`
  // modifier on the property itself) AND nullable (may be present with a
  // literal `null` value). Dropping the null member here previously
  // produced `chunk_count?: number`, which lets consumers dereference a
  // value that can actually be `null` at runtime.
  if (Array.isArray(schema.anyOf)) {
    const hasNull = schema.anyOf.some((member) => member.type === 'null');
    const memberTypes = schema.anyOf
      .filter((member) => member.type !== 'null')
      .map((member) => getTypeString(member));
    const unique = [...new Set(memberTypes)];
    if (unique.length === 0) return 'any';
    return hasNull ? `${unique.join(' | ')} | null` : unique.join(' | ');
  }

  switch (schema.type) {
    case 'string':
      return schema.enum ? enumLiteralUnion(schema) : 'string';
    case 'number':
      return 'number';
    case 'integer':
      return 'number';
    case 'boolean':
      return 'boolean';
    case 'array': {
      if (!schema.items) return 'unknown[]';
      const itemType = getTypeString(schema.items);
      // Parenthesize union item types so `(string | number)[]` doesn't
      // silently become `string | number[]` (parsed as `string | (number[])`).
      return itemType.includes('|') ? `(${itemType})[]` : `${itemType}[]`;
    }
    case 'object':
      return 'Record<string, unknown>';
    default:
      return 'unknown';
  }
}

// Extract reference name from $ref
function getRefName(schema) {
  if (schema.$ref) {
    const parts = schema.$ref.split('/');
    return parts[parts.length - 1];
  }
  return 'unknown';
}

// Convert kebab-case to camelCase
function camelize(str) {
  return str
    .toLowerCase()
    .replace(/([-_][a-z])/g, g => g.toUpperCase().replace('-', '').replace('_', ''));
}

// Main execution
(async () => {
  try {
    const schema = await fetchOpenAPI();
    const code = generateTypes(schema);
    
    fs.writeFileSync(OUTPUT_FILE, code, 'utf-8');
    console.log(`✅ Types generated successfully: ${OUTPUT_FILE}`);
    console.log(`📦 Generated ${(code.match(/export/g) || []).length} exports`);
    process.exit(0);
  } catch (error) {
    console.error(`❌ Error generating types: ${error.message}`);
    process.exit(1);
  }
})();
