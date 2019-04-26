#!/usr/bin/env python3

import inspect

from bert.tasks import iter_tasks

def make_table_row(row, widths):
    return "  ".join(r.ljust(w) for w, r in zip(widths, row))

def task_schema_doc(task, schema):
    if schema is None or not task.schema_doc:
        return ""
    elif task.schema_doc is True:
        table = [("Name", "Default", "Description")]
        for name, varobj in schema.values.items():
            default = varobj.default
            if default is None:
                default = "*None*"
            elif default is True:
                default = "yes"
            elif default is False:
                default = "no"
            else:
                default = str(default)
            varhelp = varobj.help
            if varhelp is None:
                varhelp = ""
            table.append((name, default, varhelp))
        widths = [max(len(r[i]) for r in table) for i in range(len(table[0]))]
        tr = "  ".join("="*w for w in widths)

        lines = [tr, make_table_row(table[0], widths), tr]
        for row in table[1:]:
            lines.append(make_table_row(row, widths))
        lines.append(tr)

        return "\n".join(lines)
    else:
        return task.schema_doc

def task_doc(task):
    doc = inspect.cleandoc(task.__doc__ or "No documentation available.")
    return "\n".join([doc, "", task_schema_doc(task, task.schema)])

def write_task_docs(fileobj, task):
    fileobj.write("%s\n"%task.task_name)
    fileobj.write("%s\n\n"%("-"*len(task.task_name)))
    fileobj.write(task_doc(task))
    fileobj.write("\n\n")

def main():
    with open("_tasks.rst", "w") as f:
        for task in sorted(iter_tasks(), key=lambda x: x.task_name):
            write_task_docs(f, task)

if __name__=='__main__':
    main()
