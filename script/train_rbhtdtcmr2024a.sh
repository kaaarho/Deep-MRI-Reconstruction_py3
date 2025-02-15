# Setting
# Train on AYL
GPUID=3

project_path="/home/jh/Deep-MRI-Reconstruction_py3"
cd ${project_path}

model_name="D5C5"
dataset_name="RBHTDTCMR2024A"

# MASK
#mask_name="fMRI_Reg_AF2_CF0.16_PE48"
#mask_name="fMRI_Reg_AF4_CF0.08_PE48"
mask_name="fMRI_Reg_AF8_CF0.04_PE48"
#mask_name="fMRI_Reg_AF16_CF0.02_PE48"

# CPHASE
#disease="AllDisease"

# DISEASE
#cphase=["systole", "diastole"]

task_name=${model_name}_${dataset_name}_${mask_name}
log_name=log_train_${task_name}.txt

# Run
rm ${log_name}

CUDA_VISIBLE_DEVICES=$GPUID \
PYTHONPATH=$(pwd) \
nohup python train_DCCNN_D5C5_RBHTDTCMR2024A.py \
--task_name ${task_name} \
--data_path /media/NAS_CMR/DTCMR/Newpipeline/Data_pickle4/Data/ \
--log_folder_path /media/NAS06/jiahao/RBHT_DTCMR_2024A/d.3.0.debug/log \
--num_epoch 21 \
--batch_size 16 \
--lr 0.001 \
--l2 1e-6 \
--undersampling_mask ${mask_name} \
--resolution_h 256 \
--resolution_w 96 \
>> ${log_name} &
