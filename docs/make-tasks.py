#!/usr/bin/env python3

import inspect

from bert.tasks import iter_tasks

def write_task_docs(fileobj, task):
    fileobj.write("%s\n"%task.task_name)
    fileobj.write("%s\n\n"%("-"*len(task.task_name)))
    fileobj.write(inspect.cleandoc(task.__doc__ or "No documentation available."))
    fileobj.write("\n\n")

def main():
    with open("_tasks.rst", "w") as f:
        for task in sorted(iter_tasks(), key=lambda x: x.task_name):
            write_task_docs(f, task)

if __name__=='__main__':
    main()
