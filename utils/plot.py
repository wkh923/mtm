import numpy as np
policy_traj = []
with open('outputs/2023-11-30/15-47-31/returns.txt', 'r') as f:
    for line in f:
        policy_traj.append(float(line.strip()))  

plan_traj = []
with open('outputs/2023-11-30/15-43-41/returns.txt', 'r') as f:
    for line in f:
        plan_traj.append(float(line.strip()))

import matplotlib.pyplot as plt
policy_traj = np.array(policy_traj)
plan_traj = np.array(plan_traj)
bins = np.histogram_bin_edges(np.concatenate((policy_traj, plan_traj)), bins=10)
# Plot histogram for file1_data
plt.hist(policy_traj, bins=bins, alpha=0.7, label='Policy Sample')
plt.hist(plan_traj, bins=bins, alpha=0.7, label='Planning Sample')
plt.axvline(x=1717.6346, color='r', linestyle='dashed', linewidth=2, label='Replay Buffer Average Return ')

# Labeling and legends
plt.xlabel('Total Return')
plt.ylabel('Frequency')
plt.title('Total Return Histogram')
plt.legend(loc='upper right')
plot_filename = 'sample_efficiency_histogram.png'
plt.savefig(plot_filename)

# Show the plot
plt.close()