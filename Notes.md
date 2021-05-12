# Family Tree 


## Logical Section

In this section, I will be stating the reasoning used to justify the code behaviour.

### Occupation

Generally people do not tend to change occupation frequently or at all. There are some cases where such a transition is
mandatory. One such example is the transition from Student to Programmer. To store such changes, **Cardinality.set_** is 
used. A to string of occupation class is pushed into the occupation variable.

### Birth

As a part of the objective, I would like to include date of births from multiple calendars. Therefore I would be using
**Cardinality.set_** with *toString* attribute of Birth class**

## Coding Section
In this section, I will be stating the actual coding implementation of a feature. These could be optimized in the future
if a better approach is known.

### Creating Relation

The code is written in such a way that the Male/Elder person of a relationship are placed in person A.
The person in place B is either wife/fiancé(Female) .The person in place C is child. This will be empty in the case of creating a
marriage/engagement relation.

### Modifying Vertex Properties

It appears that there is no native [support](https://github.com/pokitdok/gremlin-python/issues/16) for the **gremlinpython** library for updating the vertex properties, therefore
the roundabout approach is taken by creating by sending the raw query directly to the gremlin server.

## Debuggin Section

Gremlin console can be connected to the current gremlin server with the following commands

```angular2html
:remote connect tinkerpop.server conf/remote.yaml

:remote console
```
