import inspect


def get_function_name():
    # Get the frame of the current function
    current_frame = inspect.currentframe()
    # Go two levels up: current_frame -> caller -> caller_of_caller
    caller_of_caller_frame = current_frame.f_back.f_back

    # Get the module name
    module = inspect.getmodule(caller_of_caller_frame)
    module_name = module.__name__ if module else None

    # Get the class name (if the function is a method)
    if "self" in caller_of_caller_frame.f_locals:
        class_name = caller_of_caller_frame.f_locals["self"].__class__.__name__
    else:
        class_name = None

    # Get the function name
    function_name = caller_of_caller_frame.f_code.co_name

    # Construct the fully qualified name
    if module_name and class_name:
        return f"{module_name}.{class_name}.{function_name}"
    elif module_name:
        return f"{module_name}.{function_name}"
    else:
        return function_name
