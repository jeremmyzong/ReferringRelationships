"""Define the referring relationship model.
"""

from config import parse_args
from keras import backend as K
from keras.applications.resnet50 import ResNet50
from keras.layers import Dense, Flatten, UpSampling2D, Reshape, Input, Activation
from keras.layers.core import Lambda, Dropout
from keras.layers.convolutional import Conv2D, Conv2DTranspose
from keras.layers.embeddings import Embedding
from keras.layers.merge import Dot, Concatenate, Multiply
from keras.models import Model

import numpy as np

class ReferringRelationshipsModel():
    """Given a relationship, this model locatlizes them.
    """

    def __init__(self, args):
        """Constructor for ReferringRelationshipModel.

        Args:
            args: the arguments specified by `config.py`.
        """
        self.input_dim = args.input_dim
        self.feat_map_dim = args.feat_map_dim
        self.hidden_dim = args.hidden_dim
        self.embedding_dim = args.embedding_dim
        self.num_predicates = args.num_predicates
        self.num_objects = args.num_objects
        self.dropout = args.dropout
        self.use_subject = args.use_subject
        self.use_predicate = args.use_predicate
        self.use_object = args.use_object
        self.feat_map_layer = args.feat_map_layer

    def build_model(self):
        """Initializes the ReferringRelationshipModel.

        Returns:
            The Keras model.
        """

        # Setup the inputs.
        input_im = Input(shape=(self.input_dim, self.input_dim, 3))
        relationship_inputs = []
        num_classes = []
        if self.use_subject:
            input_sub = Input(shape=(1,))
            relationship_inputs.append(input_sub)
            num_classes.append(self.num_objects)
        if self.use_predicate:
            input_pred = Input(shape=(1,))
            relationship_inputs.append(input_pred)
            num_classes.append(self.num_predicates)
        if self.use_object:
            input_obj = Input(shape=(1,))
            relationship_inputs.append(input_obj)
            num_classes.append(self.num_objects)

        # Map the inputs to the outputs.
        im_features = self.build_image_model(input_im)
        im_features = Dropout(self.dropout)(im_features)
        im_features = Conv2D(self.hidden_dim, 1, padding='same')(im_features)
        im_features = Dropout(self.dropout)(im_features)
        rel_features = self.build_relationship_model(relationship_inputs, num_classes)
        rel_features = Dropout(self.dropout)(rel_features)
        subjects_att = Dense(self.hidden_dim, activation='relu')(rel_features)
        objects_att = Dense(self.hidden_dim, activation='relu')(rel_features)
        subjects_att = Dropout(self.dropout)(subjects_att)
        objects_att = Dropout(self.dropout)(objects_att)
        subject_regions = self.build_attention_layer(im_features, subjects_att, "subject")
        object_regions = self.build_attention_layer(im_features, objects_att, "object")
        model_inputs = [input_im] + relationship_inputs
        model = Model(inputs=model_inputs, outputs=[subject_regions, object_regions])
        return model

    def build_image_model(self, input_im):
        """Grab the image features.

        Args:
            input_im: The input image to the model.

        Returns:
            The image feature map.
        """
        base_model = ResNet50(weights='imagenet',
                              include_top=False,
                              input_shape=(self.input_dim, self.input_dim, 3))
        for layer in base_model.layers:
            layer.trainable = False
        output = base_model.get_layer(self.feat_map_layer).output
        image_branch = Model(inputs=base_model.input, outputs=output)
        im_features = image_branch(input_im)
        return im_features

    def build_relationship_model(self, relationship_inputs, num_classes):
        """Converts the input relationship into a feature space.

        Args:
            relationship_inputs: A list of inputs to the model. Can contains
              input_sub, input_pred or input_obj depending on the args.
            num_classes: A list containing how many categories each input can
              take in the relatinoship_inputs list. Used to initialize the
              embedding layer.

        Returns:
            The feature representation for the relationship.
        """
        embeddings = []
        for rel_input, num_categories in zip(relationship_inputs, num_classes):
            embedding_layer = Embedding(num_categories,
                                        self.embedding_dim,
                                        input_length=1)
            embeddings.append(embedding_layer(rel_input))

        # Concatenate the inputs if there are more than 1.
        if len(embeddings) > 1:
            concatenated_inputs = Concatenate(axis=2)(embeddings)
        else:
            concatenated_inputs = embeddings[0]
        concatenated_inputs = Dropout(self.dropout)(concatenated_inputs)
        rel_features = Dense(self.hidden_dim, activation="relu")(concatenated_inputs)
        return rel_features

    def build_frac_strided_transposed_conv_layer(self, conv_layer):
        res = UpSampling2D(size=(2, 2))(conv_layer)
        res = Conv2DTranspose(1, 3, padding='same')(res)
        return res

    def build_upsampling_layer(self, feature_map, layer_name):
        upsampling_factor = self.input_dim / self.feat_map_dim
        k = int(np.log(upsampling_factor) / np.log(2))
        res = feature_map
        for i in range(k):
            res = self.build_frac_strided_transposed_conv_layer(res)
        predictions = Activation('sigmoid')(res)
        predictions = Flatten(name=layer_name)(predictions)
        return predictions

    def build_attention_layer(self, images, relationships, layer_name):
        merged = Multiply()([images, relationships])
        merged = Lambda(lambda x: K.sum(x, axis=3, keepdims=True))(merged)
        predictions = self.build_upsampling_layer(merged, layer_name)
        return predictions


if __name__ == "__main__":
    args = parse_args()
    rel = ReferringRelationshipsModel(args)
    model = rel.build_model()
    model.summary()
