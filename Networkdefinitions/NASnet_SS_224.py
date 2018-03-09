def inference(images, isTrainingRun = True, isTrainingFromScratch=True):

  images = tf.to_float(images)
 

  with slim.arg_scope(nasnet.nasnet_mobile_arg_scope()):
    probabilities, end_points  = nasnet.build_nasnet_mobile(images, num_classes=1001, is_training=False)

  if isTrainingFromScratch:
    variables_to_restore = slim.get_variables_to_restore(exclude=['build_nasnet_mobile/AuxLogits', 'build_nasnet_mobile/Logits'])
    backbone_init_fn = slim.assign_from_checkpoint_fn(checkpoint_file, variables_to_restore)


  with tf.name_scope('COMMON_ENTRANCE'):
    with tf.variable_scope('COMMON_ENTRANCE'):

      CME_GCN_1 = LayerBlocks.global_conv_module(end_points['Cell_11'], end_points['Cell_11'].get_shape()[3], name='CME_GCN_1', k=5) 
      CME_Atrous_1 = LayerBlocks.atrousPyramid_small(end_points['Cell_11'], name= "CME_Atrous_1", allow_r16=False, training=isTrainingRun) 

      CME =  tf.concat([CME_Atrous_1, CME_GCN_1], 3)
      print("end_points['Cell_11']  : " + str(end_points['Cell_11'].get_shape()[:]))
      print("CME_GCN_1  : " + str(CME_GCN_1.get_shape()[:]))
      print("CME_Atrous_1  : " + str(CME_Atrous_1.get_shape()[:]))
      print("CME  : " + str(CME.get_shape()[:]))
      CME = tf.layers.conv2d(CME, 1536 , (1,1), activation= tf.nn.relu, padding='VALID')

  with tf.name_scope('NEUTRAL_Branch'):
    with tf.variable_scope('NEUTRAL_Branch'):
      n_up_1 = LayerBlocks.up_project(CME, size=[3, 3, 1536, 96], id = 'n_2x_a', stride = 1, training=isTrainingRun)
      n_up_2 = LayerBlocks.up_project(n_up_1, size=[3, 3, 96, 64], id = 'n_2x_b', stride = 1, training=isTrainingRun)
      n_up_3 = LayerBlocks.up_project(n_up_2, size=[3, 3, 64, 64], id = 'n_2x_c', stride = 1, training=isTrainingRun)
      n_up_4 = LayerBlocks.up_project(n_up_3, size=[3, 3, 64, 56], id = 'n_2x_d', stride = 1, training=isTrainingRun) 
      n_up_5 = LayerBlocks.up_project(n_up_4, size=[3, 3, 56, 20], id = 'n_2x_e', stride = 1, training=isTrainingRun)

      print("n_up_1  : " + str(n_up_1.get_shape()[:]))
      print("n_up_2 : " + str(n_up_2.get_shape()[:]))
      print("n_up_3 : " + str(n_up_3.get_shape()[:]))
      print("n_up_4 : " + str(n_up_4.get_shape()[:]))
      print("n_up_5 : " + str(n_up_5.get_shape()[:]))



  with tf.name_scope('SEMANCTIC_Branch'):
    with tf.variable_scope('SEMANCTIC_Branch'):
      s_up_1 = LayerBlocks.boundary_refine(CME, name='BR_s_up_1', training=isTrainingRun)    
      s_up_1 = slim.convolution2d_transpose(s_up_1, 96, [3,3], [4,4], activation_fn=tf.nn.relu) 

      dil_s_up_1 = tf.contrib.layers.conv2d(s_up_1, 48, kernel_size=3, rate=2)
      sem_mix_1 = tf.concat([s_up_1, n_up_2, dil_s_up_1], 3)

      s_up_2= LayerBlocks.boundary_refine(sem_mix_1, name='BR_s_up_2', training=isTrainingRun)
      s_up_2 = slim.convolution2d_transpose(s_up_2, 64, [3,3], [2,2], activation_fn=tf.nn.relu) 

      dil_s_up_2 = tf.contrib.layers.conv2d(s_up_2, 32, kernel_size=3, rate=8)
      sem_mix_2 = tf.concat([s_up_2, n_up_3, dil_s_up_2], 3)

      s_up_3 = LayerBlocks.boundary_refine(sem_mix_2, name='BR_s_up_3' ,training=isTrainingRun)
      s_up_3 = slim.convolution2d_transpose(s_up_3, 64, [5,5], [2,2], activation_fn=tf.nn.relu)

      dil_s_up_3 = tf.contrib.layers.conv2d(s_up_3, 32, kernel_size=3, rate=16)
      sem_mix_3 = tf.concat([s_up_3, n_up_4, dil_s_up_3], 3)

      s_up_4 = LayerBlocks.boundary_refine(sem_mix_3, name='BR_s_up_4', training=isTrainingRun)
      s_up_4 = slim.convolution2d_transpose(s_up_4, 64, [5,5], [2,2], activation_fn=tf.nn.relu) 

      dil_s_up_4 = tf.contrib.layers.conv2d(s_up_4, 32, kernel_size=3, rate=16)
      sem_mix_4 = tf.concat([s_up_4, n_up_5, dil_s_up_4], 3)

      semantic_endpoint = tf.layers.conv2d(sem_mix_4, NUMBER_OF_CLASSES , (1,1), activation=tf.nn.relu, padding='VALID')
      semantic_endpoint = LayerBlocks.boundary_refine(semantic_endpoint, name='BR_semantic_endpoint' ,training=isTrainingRun)


      print("s_up_1  : " + str(s_up_1.get_shape()[:]))
      print("s_up_2 : " + str(s_up_2.get_shape()[:]))
      print("s_up_3 : " + str(s_up_3.get_shape()[:]))
      print("s_up_4 : " + str(s_up_4.get_shape()[:]))
      print("Semantic before resize : " + str(semantic_endpoint.get_shape()[:]))


  if isTrainingFromScratch:
    return backbone_init_fn, semantic_endpoint

  return semantic_endpoint

def loss_fn(logits, annotation_batch):
  """Calculates the loss from the logits and the labels.
  Args:
    logits: Logits Tensor 
    annotation_batch: Traind-ID's corrected label Tensor
  Returns:
    loss: Loss tensor of type float.
  """

  with tf.variable_scope("Loss"):
    semantic_endpoint_proc= tf.reshape(logits, [-1, NUMBER_OF_CLASSES])
    annotation_batch = tf.squeeze(annotation_batch, squeeze_dims=[3]) # reducing the channel dimension.
    annotation_batch_proc = tf.one_hot(annotation_batch, depth=NUMBER_OF_CLASSES)
    gt = tf.reshape(annotation_batch_proc, [-1, NUMBER_OF_CLASSES])


    xentropy_mean = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(logits=semantic_endpoint_proc, labels=gt), name='xentropy_mean')
  
    reg_loss_col = tf.GraphKeys.REGULARIZATION_LOSSES
    weight_loss = tf.add_n(tf.get_collection(reg_loss_col),name='reg_loss')


    tf.summary.scalar('xentropy_mean', xentropy_mean)
    tf.summary.scalar('weight_loss', weight_loss)


  return  xentropy_mean + weight_loss 
