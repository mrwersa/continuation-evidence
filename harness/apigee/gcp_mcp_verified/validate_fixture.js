// Execute the bundle's actual validator, not a reimplementation of its regex.
const fs = require('node:fs');
const vm = require('node:vm');
const payload = JSON.parse(fs.readFileSync(0, 'utf8'));
const source = fs.readFileSync(payload.source, 'utf8');
const results = payload.cases.map(item => {
  const variables = {
    'request.content': JSON.stringify(item.request),
    'request.header.x-task-id': item.task,
  };
  vm.runInNewContext(source, {context: {
    getVariable: name => variables[name],
    setVariable: (name, value) => {variables[name] = value;},
  }}, {timeout: 200});
  return {valid: variables['smoke.valid'],
    task: variables['smoke.task'], amount: variables['smoke.amount']};
});
process.stdout.write(JSON.stringify(results));
