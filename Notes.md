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

### Gender

In this application, gender is a binary option which refers to the sex assigned at birth by the doctor. Male and Female
are the two options one can have.

### Adoption

As per the rules in our family, the lastname of the person adopted will be changed to the lastname of the family
adopting the child. The lastname of the family will be the last name of the Husband of the family. This will be the
default behaviour and lastname should be changed back if the need be. In the case of homosexual marriages, there is no
lastname attribute passed.

### Facial Recognition

In this project, [face_recognition](https://pypi.org/project/face-recognition/) library is used for recognizing faces.
The problem with face recognition in this application is the variation of a face with the change in time. Therefore
multiple faces should be stored for recognizing the person accurately or confidently. This package also accounts for
faces that are captured from a side angle too. It is mentioned that this model is trained for adult faces, therefore
children's faces are not accurately predicted. Therefore, the threshold for younger people in the family tree is kept at
a much lower value than the default 0.6 .

## Coding Section

In this section, I will be stating the actual coding implementation of a feature. These could be optimized in the future
if a better approach is known. Major part of the gremlin based logic is being migrated to groovy scripts.

### Graphs

To create new graphs, change the keyspace of casssandra.By changing keyspace, we can build this into an application
which supports graphs of different people.

*clone()* is used to repeat a piece of gremlin functionality again later in the code.

### Edge relations

Under ideal conditions, the birth and death related information must have been on the edge connecting to the
corresponding location node. This is not implemented because some birth locations of the ancestors may not be known.
That model of storing information would not allow date of birth because place of birth is unknown.

### Modifying Vertex Properties

It appears that there is no native [support](https://github.com/pokitdok/gremlin-python/issues/16) for the **
gremlinpython** library for updating the vertex properties, therefore the roundabout approach is taken by creating by
sending the raw query directly to the gremlin server.

## Debuggin Section

Gremlin console can be connected to the current gremlin server with the following commands

```angular2html
:remote connect tinkerpop.server conf/remote.yaml

:remote console
```
