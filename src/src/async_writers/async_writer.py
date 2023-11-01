class AsyncWriterMeta(type):
    """
    A Parser metaclass that will be used for parser class creation.
    """
    def __instancecheck__(cls, instance):
        return cls.__subclasscheck__(type(instance))

    def __subclasscheck__(cls, subclass):
        return (
            hasattr(subclass, 'write_rows') and callable(subclass.write_rows)
        )

class UpdatedAsyncWriterInterface(metaclass=AsyncWriterMeta):
    """This interface is used for concrete classes to inherit from.
    There is no need to define the ParserMeta methods as any class
    as they are implicitly made available via .__subclasscheck__().
    import .async_writer
    """
    pass
